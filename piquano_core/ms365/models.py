"""
Shared MS365-Models: MailAccount, OAuthFlowState, MailSubscription.

Referenzieren nur AUTH_USER_MODEL — keine App-spezifischen FKs.
db_table ist explizit gesetzt, damit bei Migration vom CRM-eigenen
ms365-Modul kein Schema-Change nötig ist.
"""

import uuid
from django.db import models
from django.conf import settings


class MailAccount(models.Model):
    STATUS_CHOICES = [
        ('connected', 'Verbunden'),
        ('needs_reauth', 'Neu verbinden nötig'),
        ('revoked', 'Entzogen'),
        ('error', 'Fehler'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mail_account',
        verbose_name='User',
    )
    upn = models.EmailField('User Principal Name', max_length=255)
    tenant_id = models.CharField('Tenant-ID', max_length=64, blank=True)

    refresh_token_enc = models.TextField('Refresh-Token (verschlüsselt)', blank=True)
    access_token_cache = models.TextField('Access-Token (Cache)', blank=True)
    access_token_expires_at = models.DateTimeField('Access-Token gültig bis', null=True, blank=True)

    inbox_delta_link = models.TextField('Inbox Delta-Link', blank=True)
    sent_delta_link = models.TextField('SentItems Delta-Link', blank=True)
    last_sync_at = models.DateTimeField('Letzter Sync', null=True, blank=True)
    last_sync_error = models.TextField('Letzter Sync-Fehler', blank=True)

    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='connected')
    connected_at = models.DateTimeField('Verbunden am', auto_now_add=True)
    updated_at = models.DateTimeField('Aktualisiert', auto_now=True)

    class Meta:
        db_table = 'ms365_mailaccount'
        verbose_name = 'Mail-Account'
        verbose_name_plural = 'Mail-Accounts'
        ordering = ['-connected_at']

    def __str__(self):
        return f"{self.upn} ({self.get_status_display()})"

    @property
    def is_healthy(self):
        return self.status == 'connected' and not self.last_sync_error


class OAuthFlowState(models.Model):
    state = models.CharField('State', max_length=128, primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='piquano_ms365_oauth_flows',
    )
    flow = models.JSONField('Flow-Dict')
    created_at = models.DateTimeField('Erstellt am', auto_now_add=True)

    class Meta:
        db_table = 'ms365_oauthflowstate'
        verbose_name = 'OAuth-Flow-State'
        verbose_name_plural = 'OAuth-Flow-States'
        indexes = [
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.user} – {self.state[:16]}…'


class MailSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        MailAccount,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name='Account',
    )
    resource = models.CharField('Resource', max_length=200)
    graph_subscription_id = models.CharField('Graph-Subscription-ID', max_length=100, unique=True)
    client_state = models.CharField('Client-State', max_length=100)
    expires_at = models.DateTimeField('Läuft ab')
    last_renewed_at = models.DateTimeField('Zuletzt verlängert', auto_now=True)
    created_at = models.DateTimeField('Erstellt am', auto_now_add=True)

    class Meta:
        db_table = 'ms365_mailsubscription'
        verbose_name = 'Mail-Subscription'
        verbose_name_plural = 'Mail-Subscriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.account.upn} – {self.resource}"
