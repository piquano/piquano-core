"""
Universelle OAuth-Views für MS365-Integration.

Enthalten: connect, callback, disconnect, notify, status (minimal).
App-spezifische Views (Postfach, Compose) bleiben in der konsumierenden App.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import oauth
from .crypto import encrypt
from .models import MailAccount, OAuthFlowState

logger = logging.getLogger(__name__)


def _credentials_configured() -> bool:
    return all([
        getattr(settings, 'MS365_CLIENT_ID', ''),
        getattr(settings, 'MS365_CLIENT_SECRET', ''),
        getattr(settings, 'MS365_TENANT_ID', ''),
        getattr(settings, 'MS365_TOKEN_ENCRYPTION_KEY', ''),
    ])


@login_required
def status(request):
    """Minimale Status-Übersicht. Apps können ein eigenes Template überschreiben."""
    account = MailAccount.objects.filter(user=request.user).first()
    return render(request, 'piquano_ms365/status.html', {
        'account': account,
        'configured': _credentials_configured(),
    })


@login_required
def connect(request):
    """OAuth-Flow starten — leitet zu Microsoft weiter."""
    if not _credentials_configured():
        messages.error(request, 'MS365-Integration ist noch nicht konfiguriert.')
        return redirect('piquano_ms365:status')

    auth_url, flow = oauth.start_flow(request)
    OAuthFlowState.objects.update_or_create(
        state=flow['state'],
        defaults={'user': request.user, 'flow': flow},
    )
    return redirect(auth_url)


@csrf_exempt
def callback(request):
    """OAuth-Callback — Authorization-Code → Tokens → MailAccount."""
    params = request.POST if request.method == 'POST' else request.GET
    logger.info('MS365 callback method=%s param-keys=%s', request.method, list(params.keys()))

    state = params.get('state', '')
    if not state:
        logger.warning('MS365 callback ohne state-Param')
        return HttpResponseBadRequest('Missing state')

    flow_state = OAuthFlowState.objects.filter(state=state).select_related('user').first()
    if not flow_state:
        logger.warning('MS365 callback: kein OAuthFlowState für state=%s...', state[:16])
        return HttpResponseBadRequest('Unknown or expired flow state')

    user = flow_state.user
    flow = flow_state.flow

    try:
        result = oauth.complete_flow(request, flow, dict(params.items()))
    except Exception as exc:
        logger.exception('MS365 complete_flow geworfen')
        flow_state.delete()
        messages.error(request, f'Verbindung fehlgeschlagen: {exc}')
        return redirect('piquano_ms365:status')

    try:
        id_claims = result.get('id_token_claims') or {}
        upn = id_claims.get('preferred_username') or id_claims.get('upn') or id_claims.get('email') or ''
        tenant_id = id_claims.get('tid', '')
        refresh_token = result.get('refresh_token', '')
        access_token = result.get('access_token', '')
        expires_in = int(result.get('expires_in', 3600))

        if not refresh_token:
            flow_state.delete()
            messages.error(request, 'Microsoft hat keinen Refresh-Token zurückgegeben.')
            return redirect('piquano_ms365:status')

        account, created = MailAccount.objects.update_or_create(
            user=user,
            defaults={
                'upn': upn,
                'tenant_id': tenant_id,
                'refresh_token_enc': encrypt(refresh_token),
                'access_token_cache': access_token,
                'access_token_expires_at': timezone.now() + timedelta(seconds=expires_in),
                'status': 'connected',
                'last_sync_error': '',
            },
        )
        logger.info('MS365 MailAccount %s upn=%s', 'erstellt' if created else 'aktualisiert', upn)
        flow_state.delete()

        messages.success(
            request,
            f'Postfach {upn} erfolgreich verbunden.' if created else f'Postfach {upn} aktualisiert.',
        )
        return redirect('piquano_ms365:status')
    except Exception as exc:
        logger.exception('MS365 callback Persistierung geworfen')
        flow_state.delete()
        messages.error(request, f'Persistierung fehlgeschlagen: {exc}')
        return redirect('piquano_ms365:status')


@login_required
def disconnect(request):
    """Verbindung trennen."""
    if request.method != 'POST':
        return redirect('piquano_ms365:status')
    MailAccount.objects.filter(user=request.user).update(
        status='revoked',
        refresh_token_enc='',
        access_token_cache='',
    )
    messages.success(request, 'Microsoft-365-Verbindung getrennt.')
    return redirect('piquano_ms365:status')


@csrf_exempt
def notify(request):
    """Webhook-Endpoint für Microsoft Graph Change Notifications."""
    if request.method == 'POST' and 'validationToken' in request.GET:
        return HttpResponse(request.GET['validationToken'], content_type='text/plain')
    # TODO: Notification verarbeiten und Delta-Sync triggern
    return HttpResponse(status=202)
