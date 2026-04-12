from django.contrib import admin
from .models import MailAccount, MailSubscription


@admin.register(MailAccount)
class MailAccountAdmin(admin.ModelAdmin):
    list_display = ('upn', 'user', 'status', 'last_sync_at', 'connected_at')
    list_filter = ('status',)
    readonly_fields = ('id', 'connected_at', 'updated_at')


@admin.register(MailSubscription)
class MailSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('account', 'resource', 'expires_at', 'last_renewed_at')
    list_filter = ('resource',)
