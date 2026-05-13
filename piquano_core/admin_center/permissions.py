"""Helper functions for permission management."""

import logging

logger = logging.getLogger("piquano.permissions")


def assign_default_permissions(user, codenames=("read", "write")):
    """No-op. Neue User erben Berechtigungen ueber ihr Team.

    Frueher wurden hier pauschal read+write User-Grants vergeben,
    was Team-Einschraenkungen komplett aushebelte. Seit 2026-05-13
    deaktiviert — Team-Permissions sind die einzige Basis,
    User-Permissions dienen nur noch fuer gezielte Ausnahmen.
    """
    return
