"""
Abstract Sync-Adapter — jede konsumierende App implementiert diesen.

Pfad zur Klasse wird in settings.MS365_SYNC_ADAPTER konfiguriert.
"""

from abc import ABC, abstractmethod


class Ms365SyncAdapter(ABC):

    @abstractmethod
    def match_message(self, msg: dict, user_email: str) -> tuple[bool, list]:
        """
        Prüft ob eine Graph-Message relevant ist.
        Returns (is_relevant, list_of_matched_entities).
        """
        ...

    @abstractmethod
    def persist_message(self, *, account, msg, folder, matched_entities, client, dry_run) -> tuple[bool, bool]:
        """
        Persistiert eine gematchte Mail im app-eigenen Model.
        Returns (created, updated).
        """
        ...

    def create_sync_log(self, **kwargs):
        """Optional: SyncLog anlegen. Default: no-op."""
        return None

    def update_sync_log(self, sync_log, **kwargs):
        """Optional: SyncLog updaten. Default: no-op."""
        if sync_log:
            for k, v in kwargs.items():
                setattr(sync_log, k, v)
            sync_log.save()
