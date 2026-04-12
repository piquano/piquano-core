"""Microsoft-Graph-Client für einen einzelnen MailAccount."""

import logging
from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone

from . import oauth
from .crypto import decrypt, encrypt
from .models import MailAccount

logger = logging.getLogger(__name__)

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'


class GraphError(Exception):
    pass


class TokenInvalidError(GraphError):
    """Refresh-Token unbrauchbar — User muss neu verbinden."""


class GraphClient:
    def __init__(self, account: MailAccount):
        self.account = account

    def _need_refresh(self) -> bool:
        if not self.account.access_token_cache:
            return True
        if not self.account.access_token_expires_at:
            return True
        return timezone.now() >= self.account.access_token_expires_at - timedelta(minutes=2)

    def _refresh(self) -> str:
        if not self.account.refresh_token_enc:
            raise TokenInvalidError('Kein Refresh-Token gespeichert.')
        refresh_token = decrypt(self.account.refresh_token_enc)
        try:
            result = oauth.refresh_access_token(refresh_token)
        except RuntimeError as exc:
            with transaction.atomic():
                MailAccount.objects.filter(pk=self.account.pk).update(
                    status='needs_reauth',
                    last_sync_error=str(exc),
                )
            raise TokenInvalidError(str(exc)) from exc

        access_token = result['access_token']
        expires_in = int(result.get('expires_in', 3600))
        new_refresh = result.get('refresh_token')

        with transaction.atomic():
            updates = {
                'access_token_cache': access_token,
                'access_token_expires_at': timezone.now() + timedelta(seconds=expires_in),
                'status': 'connected',
                'last_sync_error': '',
            }
            if new_refresh:
                updates['refresh_token_enc'] = encrypt(new_refresh)
            MailAccount.objects.filter(pk=self.account.pk).update(**updates)
            for k, v in updates.items():
                setattr(self.account, k, v)
        return access_token

    def access_token(self) -> str:
        if self._need_refresh():
            return self._refresh()
        return self.account.access_token_cache

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.access_token()}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def get(self, path_or_url: str, **params) -> dict:
        url = path_or_url if path_or_url.startswith('http') else f'{GRAPH_BASE}{path_or_url}'
        resp = requests.get(url, headers=self._headers(), params=params or None, timeout=30)
        return self._handle(resp)

    def post(self, path: str, json: dict | None = None) -> dict:
        url = f'{GRAPH_BASE}{path}'
        resp = requests.post(url, headers=self._headers(), json=json, timeout=30)
        return self._handle(resp)

    def patch(self, path: str, json: dict | None = None) -> dict:
        url = f'{GRAPH_BASE}{path}'
        resp = requests.patch(url, headers=self._headers(), json=json, timeout=30)
        return self._handle(resp)

    def delete(self, path: str) -> None:
        url = f'{GRAPH_BASE}{path}'
        resp = requests.delete(url, headers=self._headers(), timeout=30)
        if resp.status_code not in (200, 202, 204):
            raise GraphError(f'DELETE {path} → {resp.status_code} {resp.text}')

    def create_and_send_draft(self, *, to, subject, body_html, cc=None, bcc=None) -> dict:
        def _recip(addrs):
            return [{'emailAddress': {'address': a}} for a in (addrs or [])]
        draft_payload = {
            'subject': subject,
            'body': {'contentType': 'HTML', 'content': body_html},
            'toRecipients': _recip(to),
            'ccRecipients': _recip(cc),
            'bccRecipients': _recip(bcc),
        }
        draft = self.post('/me/messages', json=draft_payload)
        draft_id = draft.get('id')
        if not draft_id:
            raise GraphError(f'create_draft hat keine id zurückgegeben: {draft}')
        url = f'{GRAPH_BASE}/me/messages/{draft_id}/send'
        resp = requests.post(url, headers=self._headers(), timeout=30)
        if resp.status_code not in (200, 202, 204):
            raise GraphError(f'send draft {draft_id} → {resp.status_code} {resp.text}')
        return draft

    def _handle(self, resp: requests.Response) -> dict:
        if resp.status_code == 401:
            self.account.access_token_expires_at = None
            raise GraphError(f'401 Unauthorized: {resp.text}')
        if resp.status_code == 429:
            retry_after = resp.headers.get('Retry-After', '?')
            raise GraphError(f'429 Throttled, Retry-After={retry_after}')
        if resp.status_code >= 400:
            raise GraphError(f'{resp.status_code} {resp.text}')
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()
