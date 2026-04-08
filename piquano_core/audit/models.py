"""
AuditLog model + DSGVO helpers.

A minimal append-only event log every PIQUANO app should plug into:

* who did what (user)
* against which object (generic FK via content_type + object_id)
* when, with optional payload diff and request metadata

Plus three DSGVO helpers any user-data export/erasure flow needs:

* :func:`export_user_data`     — collect everything tied to an email
* :func:`anonymize_user_data`  — pseudonymize personal fields per subject
* :func:`lock_user_data`       — set ``is_locked=True`` on matching rows

To use, add ``"piquano_core.audit"`` to ``INSTALLED_APPS`` and run migrations
in the consuming app.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Iterator

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from piquano_core.utils import get_client_ip, models_with_field

logger = logging.getLogger(__name__)


class AuditLog(models.Model):
    """Append-only log of user-facing actions."""

    class Action(models.TextChoices):
        CREATE = "create", "Erstellt"
        UPDATE = "update", "Geändert"
        DELETE = "delete", "Gelöscht"
        VIEW = "view", "Angesehen"
        EXPORT = "export", "Exportiert"
        LOGIN = "login", "Login"
        OTHER = "other", "Sonstiges"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # Generic FK to the affected object (optional).
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    # Free-form details (e.g. field-level diff).
    payload = models.JSONField(default=dict, blank=True)

    # Request metadata.
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Optional human-readable summary.
    summary = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self):
        who = self.user.get_username() if self.user else "system"
        return f"{self.timestamp:%Y-%m-%d %H:%M} {who} {self.action}"

    @classmethod
    def record(
        cls,
        action: str,
        user=None,
        target=None,
        payload: dict | None = None,
        request=None,
        summary: str = "",
    ) -> AuditLog:
        """Convenience constructor that pulls IP/UA from a request if given."""
        kwargs: dict = {
            "action": action,
            "user": user,
            "payload": payload or {},
            "summary": summary,
        }
        if target is not None:
            kwargs["content_type"] = ContentType.objects.get_for_model(target.__class__)
            kwargs["object_id"] = target.pk
        if request is not None:
            kwargs["ip_address"] = get_client_ip(request)
            kwargs["user_agent"] = request.META.get("HTTP_USER_AGENT", "")
        return cls.objects.create(**kwargs)


# ---------------------------------------------------------------------------
# DSGVO helpers
# ---------------------------------------------------------------------------

# Default page size when streaming export rows; chosen to bound peak memory
# at ~ a few MB regardless of how many rows match.
EXPORT_CHUNK_SIZE = 1000


def export_user_data(
    email: str,
    models_to_scan: Iterable[type[models.Model]],
) -> Iterator[tuple[str, list[dict]]]:
    """Stream every row whose ``email`` matches the given address.

    Yields ``(model_label, chunk)`` tuples in pages of ``EXPORT_CHUNK_SIZE``,
    so callers can write incrementally to a JSON/ZIP stream without loading
    everything into memory. Only models with a concrete ``email`` field are
    scanned.
    """
    for model, _ in models_with_field(models_to_scan, "email"):
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        qs = model.objects.filter(email=email).values()
        chunk: list[dict] = []
        for row in qs.iterator(chunk_size=EXPORT_CHUNK_SIZE):
            chunk.append(row)
            if len(chunk) >= EXPORT_CHUNK_SIZE:
                yield label, chunk
                chunk = []
        if chunk:
            yield label, chunk


def _pseudonym_email(email: str) -> str:
    """Stable per-subject pseudonym so FK joins on email don't collapse."""
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
    return f"anon-{digest}@piquano.invalid"


def anonymize_user_data(
    email: str,
    models_to_scan: Iterable[type[models.Model]],
    fields_to_clear: tuple[str, ...] = (),
) -> int:
    """Pseudonymize personal fields on every row matching the email.

    Replaces the email with a deterministic per-subject pseudonym (so joins on
    email continue to map all of one subject's records to one bucket — without
    leaking the original address) and clears the named ``fields_to_clear`` if
    the model has them. Returns the number of rows touched.

    Apps must pass their own ``fields_to_clear`` — defaults are intentionally
    empty so this library doesn't impose a domain-specific PII schema.
    """
    pseudonym = _pseudonym_email(email)
    touched = 0
    for model, field_names in models_with_field(models_to_scan, "email"):
        update_kwargs: dict = {"email": pseudonym}
        for field in fields_to_clear:
            if field in field_names:
                update_kwargs[field] = ""
        touched += model.objects.filter(email=email).update(**update_kwargs)
    return touched


def lock_user_data(
    email: str,
    models_to_scan: Iterable[type[models.Model]],
    lock_field: str = "is_locked",
) -> int:
    """Mark records as legally locked (DSGVO Art. 18).

    Sets ``lock_field=True`` on every model that has both an ``email`` and a
    ``lock_field`` column. Compatible with the existing CRM ``Contact.is_locked``
    convention.
    """
    touched = 0
    for model, field_names in models_with_field(models_to_scan, "email"):
        if lock_field not in field_names:
            continue
        touched += model.objects.filter(email=email).update(**{lock_field: True})
    return touched
