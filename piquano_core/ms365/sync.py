"""
Generische Sync-Engine für MS365 — delegiert an den konfigurierten Adapter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from .graph import GraphClient, GraphError, TokenInvalidError
from .models import MailAccount

logger = logging.getLogger(__name__)

DELTA_SELECT_FIELDS = ",".join(
    [
        "id",
        "internetMessageId",
        "conversationId",
        "subject",
        "bodyPreview",
        "from",
        "sender",
        "toRecipients",
        "ccRecipients",
        "replyTo",
        "receivedDateTime",
        "sentDateTime",
        "hasAttachments",
    ]
)

DEFAULT_BACKFILL_DAYS = 30


def get_adapter():
    path = getattr(settings, "MS365_SYNC_ADAPTER", "")
    if not path:
        raise ImproperlyConfigured("MS365_SYNC_ADAPTER muss in settings gesetzt sein.")
    return import_string(path)()


@dataclass
class FolderSyncResult:
    folder: str
    fetched: int = 0
    matched: int = 0
    persisted_new: int = 0
    persisted_updated: int = 0
    skipped_no_match: int = 0
    failed: int = 0
    sample_subjects: list[str] = field(default_factory=list)

    def add_sample(self, subject: str) -> None:
        if len(self.sample_subjects) < 5 and subject:
            self.sample_subjects.append(subject[:80])


def _delta_link_field(folder: str) -> str:
    return "inbox_delta_link" if folder == "Inbox" else "sent_delta_link"


def _build_initial_path(folder: str, backfill_days: int) -> str:
    since = (timezone.now() - timedelta(days=backfill_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"/me/mailFolders/{folder}/messages/delta"
        f"?$select={DELTA_SELECT_FIELDS}"
        f"&$top=50"
        f"&$filter=receivedDateTime ge {since}"
    )


def _process_page(*, account, folder, page, result, client, adapter, dry_run):
    for msg in page.get("value") or []:
        result.fetched += 1
        try:
            ok, matched = adapter.match_message(msg, account.upn)
        except Exception:
            logger.exception("Matcher-Fehler bei Message %s", msg.get("id"))
            result.failed += 1
            continue

        if not ok:
            result.skipped_no_match += 1
            continue

        result.matched += 1
        try:
            created, updated = adapter.persist_message(
                account=account,
                msg=msg,
                folder=folder,
                matched_entities=matched,
                client=client,
                dry_run=dry_run,
            )
        except Exception:
            logger.exception("Persistierung von %s fehlgeschlagen", msg.get("id"))
            result.failed += 1
            continue

        if created:
            result.persisted_new += 1
        elif updated:
            result.persisted_updated += 1
        result.add_sample(msg.get("subject") or "(ohne Betreff)")


def run_folder_sync(
    account: MailAccount,
    folder: str = "Inbox",
    *,
    backfill_days: int = DEFAULT_BACKFILL_DAYS,
    dry_run: bool = False,
    full_resync: bool = False,
    adapter=None,
) -> FolderSyncResult:
    if adapter is None:
        adapter = get_adapter()
    result = FolderSyncResult(folder=folder)
    client = GraphClient(account)
    delta_field = _delta_link_field(folder)
    saved_delta_link = getattr(account, delta_field) if not full_resync else ""

    if saved_delta_link:
        next_url = saved_delta_link
        logger.info("MS365 sync: %s startet vom delta_link", folder)
    else:
        next_url = _build_initial_path(folder, backfill_days)
        logger.info("MS365 sync: %s Backfill für %s Tage", folder, backfill_days)

    final_delta_link = ""
    try:
        while next_url:
            page = client.get(next_url)
            _process_page(
                account=account,
                folder=folder,
                page=page,
                result=result,
                client=client,
                adapter=adapter,
                dry_run=dry_run,
            )
            next_url = page.get("@odata.nextLink", "")
            if not next_url:
                final_delta_link = page.get("@odata.deltaLink", "")
    except TokenInvalidError:
        raise
    except GraphError as exc:
        logger.error("MS365 sync: Graph-Fehler: %s", exc)
        raise

    if not dry_run:
        with transaction.atomic():
            updates = {"last_sync_at": timezone.now(), "last_sync_error": ""}
            if final_delta_link:
                updates[delta_field] = final_delta_link
            MailAccount.objects.filter(pk=account.pk).update(**updates)
            for k, v in updates.items():
                setattr(account, k, v)

    return result


def run_full_sync(
    account: MailAccount,
    *,
    backfill_days: int = DEFAULT_BACKFILL_DAYS,
    dry_run: bool = False,
    full_resync: bool = False,
) -> dict[str, FolderSyncResult]:
    adapter = get_adapter()
    sync_log = adapter.create_sync_log(source="ms365", action="sync", status="running")

    results: dict[str, FolderSyncResult] = {}
    error_message = ""
    try:
        for folder in ("Inbox", "SentItems"):
            try:
                results[folder] = run_folder_sync(
                    account,
                    folder=folder,
                    backfill_days=backfill_days,
                    dry_run=dry_run,
                    full_resync=full_resync,
                    adapter=adapter,
                )
            except (GraphError, TokenInvalidError) as exc:
                error_message = f"{folder}: {exc}"
                logger.exception("MS365 sync %s fehlgeschlagen", folder)
                continue
    finally:
        if sync_log is not None:
            totals = {
                "fetched": sum(r.fetched for r in results.values()),
                "matched": sum(r.matched for r in results.values()),
                "persisted_new": sum(r.persisted_new for r in results.values()),
                "persisted_updated": sum(r.persisted_updated for r in results.values()),
                "skipped_no_match": sum(r.skipped_no_match for r in results.values()),
                "failed": sum(r.failed for r in results.values()),
            }
            adapter.update_sync_log(
                sync_log,
                records_processed=totals["fetched"],
                records_created=totals["persisted_new"],
                records_updated=totals["persisted_updated"],
                records_failed=totals["failed"],
                details={
                    "account_upn": account.upn,
                    "totals": totals,
                    "per_folder": {
                        f: {
                            "fetched": r.fetched,
                            "matched": r.matched,
                            "new": r.persisted_new,
                            "updated": r.persisted_updated,
                            "skipped": r.skipped_no_match,
                            "failed": r.failed,
                        }
                        for f, r in results.items()
                    },
                    "error": error_message,
                },
                status="failed" if error_message else "completed",
                completed_at=timezone.now(),
            )

    if error_message and not results:
        MailAccount.objects.filter(pk=account.pk).update(
            last_sync_error=error_message[:1000],
        )

    return results
