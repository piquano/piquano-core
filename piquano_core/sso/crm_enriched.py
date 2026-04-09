"""
CRM-enriched Authelia middleware.

Sibling of :class:`AutheliaRemoteUserMiddleware` that ships a default
implementation of :meth:`enrich_from_crm`. After Authelia has authenticated
the user (and the row in the local ``auth_user`` table has been created or
synced), this middleware fetches the canonical profile from the CRM via
:class:`piquano_core.crm_client.CRMClient` and copies the standard fields
onto ``request.user``.

Apps that want CRM-master semantics for user data — Phase 0.J/0.K
Pull-Architektur — should put this class in their ``MIDDLEWARE`` instead
of the parent. Apps that don't (CRM itself, anything pre-0.J) keep using
``AutheliaRemoteUserMiddleware``.

Required settings (read by ``CRMClient.from_settings``):

* ``PIQUANO_CRM_BASE_URL``    — e.g. ``https://crm.piquano.com``
* ``PIQUANO_CRM_API_TOKEN``   — DRF token issued by the CRM

Failure mode: if the CRM is unreachable or the user is unknown there, we
log a warning and let the request through with whatever Authelia provided.
A CRM outage must NOT lock everyone out of the app — Authelia is the
authentication of record, the CRM is only the profile-data store.

Standard fields synced from CRM (always):

* ``first_name``
* ``last_name``
* ``email``

Conditional fields synced ONLY if the local user model has them
(``hasattr`` check, no schema assumptions about custom user models):

* ``phone``
* ``avatar_url``

Roles, teams, ``is_active``, ``is_staff``, and any other privileged
attributes are deliberately NOT synced here — they belong to either the
auth layer (Authelia groups → ``is_staff``, handled by the parent) or
the per-app authorization model.
"""

from __future__ import annotations

import logging

from .middleware import AutheliaProfile, AutheliaRemoteUserMiddleware

logger = logging.getLogger(__name__)

# Fields that exist on django.contrib.auth.models.AbstractUser and so are
# safe to write unconditionally on every consumer.
_STANDARD_FIELDS = ("first_name", "last_name", "email")

# Fields that some PIQUANO apps add to their custom user model. We only
# touch them if hasattr() confirms they exist — keeps the middleware
# usable with the stock Django User.
_OPTIONAL_FIELDS = ("phone", "avatar_url")


class AutheliaCRMRemoteUserMiddleware(AutheliaRemoteUserMiddleware):
    """Authelia middleware that hydrates the user from the CRM API.

    Inherits all auto-provisioning and group-syncing behavior from
    :class:`AutheliaRemoteUserMiddleware` and only overrides
    :meth:`enrich_from_crm`.
    """

    def enrich_from_crm(self, user, profile: AutheliaProfile) -> None:
        # Late imports keep piquano_core.sso importable in test contexts
        # that don't configure the CRM client (e.g. unit tests for the
        # parent middleware).
        from piquano_core.crm_client import CRMClient, CRMClientError, CRMClientNotFound

        try:
            client = CRMClient.from_settings()
        except CRMClientError as exc:
            logger.warning(
                "CRM client not configured, skipping enrich for %s: %s",
                profile.username,
                exc,
            )
            return

        try:
            data = client.get_user(profile.username)
        except CRMClientNotFound:
            # User exists in Authelia but not in the CRM. Legitimate during
            # rollout — leave the Authelia-derived fields in place.
            logger.info("CRM has no record for %s, keeping Authelia data", profile.username)
            return
        except CRMClientError as exc:
            # Network/5xx/timeout — never lock the user out.
            logger.warning("CRM enrich failed for %s: %s", profile.username, exc)
            return

        update_fields: list[str] = []

        for field in _STANDARD_FIELDS:
            new_value = data.get(field)
            if new_value is None:
                continue
            if getattr(user, field, None) != new_value:
                setattr(user, field, new_value)
                update_fields.append(field)

        for field in _OPTIONAL_FIELDS:
            if not hasattr(user, field):
                continue
            new_value = data.get(field)
            if new_value is None:
                continue
            if getattr(user, field) != new_value:
                setattr(user, field, new_value)
                update_fields.append(field)

        if update_fields:
            user.save(update_fields=update_fields)
            logger.debug("CRM-enriched %s: %s", profile.username, ", ".join(update_fields))
