"""
Authelia SSO middleware for Django.

Reads the ``Remote-User`` header set by Authelia's forward auth and
authenticates the Django user transparently. Auto-provisions on first
sight, syncs profile fields on subsequent requests.

Subclass and override :meth:`get_role_for_groups` for app-specific role
mapping.

Required headers (set by nginx ``proxy_set_header``): ``Remote-User``
(login name, required), ``Remote-Name``, ``Remote-Email``, ``Remote-Groups``
(comma-separated).

Note: ``request.user`` is set directly without ``django.contrib.auth.login()``
because Authelia is the session of record. If you switch to a hybrid model,
populate ``user.backend`` and call ``auth.login()``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutheliaProfile:
    """Parsed Authelia headers from a single request."""

    username: str
    display_name: str
    email: str
    groups: frozenset[str]

    @property
    def first_name(self) -> str:
        parts = self.display_name.strip().split(None, 1)
        return parts[0] if parts else ""

    @property
    def last_name(self) -> str:
        parts = self.display_name.strip().split(None, 1)
        return parts[1] if len(parts) > 1 else ""

    @classmethod
    def from_request(cls, request) -> AutheliaProfile | None:
        username = request.META.get("HTTP_REMOTE_USER", "").strip()
        if not username:
            return None
        groups_raw = request.META.get("HTTP_REMOTE_GROUPS", "")
        groups = frozenset(g.strip() for g in groups_raw.split(",") if g.strip())
        return cls(
            username=username,
            display_name=request.META.get("HTTP_REMOTE_NAME", "").strip(),
            email=request.META.get("HTTP_REMOTE_EMAIL", "").strip(),
            groups=groups,
        )


class AutheliaRemoteUserMiddleware:
    """Authenticate users via the ``Remote-User`` header from Authelia.

    Must run after ``SessionMiddleware`` and ``AuthenticationMiddleware``.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.User = get_user_model()
        self.admin_group = getattr(settings, "PIQUANO_AUTH_ADMIN_GROUP", "admins")
        self.sync_interval = getattr(settings, "PIQUANO_AUTH_SYNC_INTERVAL", 3600)

    def __call__(self, request):
        profile = AutheliaProfile.from_request(request)
        if profile:
            user = self._authenticate(profile)
            if user is not None:
                request.user = user
        return self.get_response(request)

    # ----- override hooks -----------------------------------------------------

    def get_role_for_groups(self, groups: frozenset[str]):
        """Map Authelia groups to a Role instance.

        Override in subclasses. Return ``None`` to skip role assignment.
        Returned instances must be saved (have a non-None ``pk``).
        """
        return None

    def is_admin(self, groups: frozenset[str]) -> bool:
        return self.admin_group in groups

    def enrich_from_crm(self, user, profile: AutheliaProfile) -> None:
        """Optional hook to hydrate user fields from the CRM API.

        Default no-op. Apps that want CRM-master semantics (Phase 0.J/0.K
        Pull-Architektur) override this and call ``CRMClient.get_user(...)``
        to fetch the canonical profile, then copy fields onto ``user``::

            from piquano_core.crm_client import CRMClient, CRMClientNotFound

            class MyMiddleware(AutheliaRemoteUserMiddleware):
                def enrich_from_crm(self, user, profile):
                    try:
                        data = CRMClient.from_settings().get_user(profile.username)
                    except CRMClientNotFound:
                        return  # CRM doesn't know this user — keep Authelia data
                    user.first_name = data.get("first_name", user.first_name)
                    user.last_name = data.get("last_name", user.last_name)
                    user.phone = data.get("phone", "")
                    user.avatar_url = data.get("avatar_url", "")

        The hook runs at the END of authentication (after create or sync).
        Saving the user is the override's responsibility — call
        ``user.save(update_fields=[...])`` if you persist changes. The
        client cache (``PIQUANO_CRM_CACHE_TTL``) bounds CRM round-trips.
        """
        return None

    # ----- internals ----------------------------------------------------------

    def _authenticate(self, profile: AutheliaProfile):
        try:
            user = self.User.objects.get(username=profile.username)
        except self.User.DoesNotExist:
            user = self._create_user(profile)
            if user is not None:
                self.enrich_from_crm(user, profile)
            return user
        if user.is_active or self._sync_user_data(user, profile):
            self.enrich_from_crm(user, profile)
            return user
        return None

    def _create_user(self, profile: AutheliaProfile):
        # get_or_create + transaction so concurrent first-time requests don't race
        # on the unique-username constraint.
        try:
            with transaction.atomic():
                user, created = self.User.objects.get_or_create(
                    username=profile.username,
                    defaults={
                        "first_name": profile.first_name,
                        "last_name": profile.last_name,
                        "email": profile.email,
                        "is_active": True,
                        "is_staff": self.is_admin(profile.groups),
                    },
                )
            if created:
                user.set_unusable_password()
                update_fields = ["password"]
                role = self.get_role_for_groups(profile.groups)
                if role is not None and hasattr(user, "role"):
                    user.role = role
                    update_fields.append("role")
                user.save(update_fields=update_fields)
                # Assign default permissions (read + write)
                try:
                    from piquano_core.admin_center.permissions import assign_default_permissions
                    assign_default_permissions(user)
                except Exception:
                    logger.warning("Could not assign default permissions for %s", profile.username)
                logger.info("Auto-provisioned user: %s", profile.username)
            return user
        except IntegrityError:
            logger.warning("Race on auto-provision: %s", profile.username)
            return self.User.objects.filter(username=profile.username).first()

    def _sync_user_data(self, user, profile: AutheliaProfile) -> bool:
        """Update changed fields. Returns True if the user is active afterwards."""
        update_fields: list[str] = []

        if profile.display_name and (
            user.first_name != profile.first_name or user.last_name != profile.last_name
        ):
            user.first_name = profile.first_name
            user.last_name = profile.last_name
            update_fields.extend(["first_name", "last_name"])

        if profile.email and user.email != profile.email:
            user.email = profile.email
            update_fields.append("email")

        is_admin_now = self.is_admin(profile.groups)
        if user.is_staff != is_admin_now:
            user.is_staff = is_admin_now
            update_fields.append("is_staff")

        role = self.get_role_for_groups(profile.groups)
        if role is not None and hasattr(user, "role") and getattr(user, "role", None) != role:
            user.role = role
            update_fields.append("role")

        # Throttle last_login to avoid a write per request.
        now = timezone.now()
        if not user.last_login or (now - user.last_login).total_seconds() > self.sync_interval:
            user.last_login = now
            update_fields.append("last_login")

        # Authelia is the source of truth — reactivate if it lets the user through.
        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")

        if update_fields:
            user.save(update_fields=update_fields)
        return user.is_active
