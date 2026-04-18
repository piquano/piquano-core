"""Helper functions for permission management."""

import logging

logger = logging.getLogger("piquano.permissions")


def assign_default_permissions(user, codenames=("read", "write")):
    """Assign default permissions (read+write) for all existing Permission objects.

    Called automatically when a new user is provisioned via SSO.
    Superusers are skipped (they get all permissions via middleware).

    Args:
        user: Django User instance
        codenames: tuple of codenames to grant (default: read + write)
    """
    if user.is_superuser:
        return

    from .models import Permission, UserPermission

    permissions = Permission.objects.filter(codename__in=codenames)
    created_count = 0
    for perm in permissions:
        _, created = UserPermission.objects.get_or_create(
            user=user,
            permission=perm,
            defaults={
                "is_granted": True,
                "granted_by": "system (auto-provision)",
            },
        )
        if created:
            created_count += 1

    if created_count:
        logger.info(
            "Default permissions assigned: user=%s, %d permissions granted",
            user.username,
            created_count,
        )
