"""Privacy consent acknowledgment — app-übergreifend via CRM-API."""

import hashlib
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").strip()
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


@require_POST
@login_required
def privacy_acknowledge(request):
    """User bestätigt Kenntnisnahme der aktuellen DSE.

    Ruft die CRM-API auf, um privacy_version und privacy_accepted_at
    zu aktualisieren. Funktioniert von jeder App aus.
    """
    from piquano_core.crm_client import CRMClient, CRMClientError

    client_ip = _get_client_ip(request)
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

    from piquano_core.admin_center.context_processors import CURRENT_DSE_VERSION

    try:
        client = CRMClient.from_settings()
        client._request(
            "PATCH",
            f"api/v1/users/{request.user.username}/privacy-acknowledge/",
            json={"ip_hash": ip_hash, "version": CURRENT_DSE_VERSION},
        )
        # Cache invalidieren damit der nächste Request die neue Version sieht
        client.invalidate_cache(f"user:{request.user.username}")
        logger.info(
            "DSGVO Art.13 Kenntnisnahme: User=%s, IP-Hash=%s",
            request.user.username,
            ip_hash,
        )
    except CRMClientError as exc:
        logger.warning(
            "Privacy acknowledge failed for %s: %s",
            request.user.username,
            exc,
        )

    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/"))
