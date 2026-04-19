"""
Knot ingestion: pulls transactions from Knot and writes them into Supabase.

Idempotent by design:
  - All transaction inserts are upserts on (provider, external_id).
  - Cursor is persisted after every page so crash recovery resumes correctly.
  - Same webhook delivered twice never produces duplicate rows.

Listener interaction:
  - New rows -> Supabase Realtime INSERT -> existing listener routes to agents.
  - UPDATE on an existing row (UPDATED_TRANSACTIONS_AVAILABLE) does NOT fire
    INSERT again -> agents not re-triggered -> no duplicate alerts.

All operations log structured events through `log` so the operator can watch
the backend terminal end-to-end.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from supabase_client import get_supabase

from . import log
from .client import KnotClient, get_knot_client
from .normalize import knot_to_transaction_row

DEFAULT_COMPANY_ID = os.getenv("FLUX_COMPANY_ID", "00000001-0000-4000-8000-000000000001")
DEFAULT_PAGE_LIMIT = int(os.getenv("KNOT_SYNC_PAGE_LIMIT", "50"))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_company_id(external_user_id: str) -> str:
    """Look up the Flux company that owns this Knot external_user_id."""
    sb = get_supabase()
    resp = (
        sb.table("companies")
        .select("id")
        .eq("knot_external_user_id", external_user_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if rows and isinstance(rows[0], dict) and rows[0].get("id"):
        return str(rows[0]["id"])
    log.warn(
        "company.fallback_to_default",
        external_user_id=external_user_id,
        default_company_id=DEFAULT_COMPANY_ID,
    )
    return DEFAULT_COMPANY_ID


def _load_cursor(external_user_id: str, merchant_id: int) -> Optional[str]:
    sb = get_supabase()
    resp = (
        sb.table("knot_sync_cursors")
        .select("cursor")
        .eq("external_user_id", external_user_id)
        .eq("merchant_id", int(merchant_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if rows and isinstance(rows[0], dict):
        return rows[0].get("cursor") or None
    return None


def _persist_cursor(external_user_id: str, merchant_id: int, cursor: Optional[str]) -> None:
    sb = get_supabase()
    sb.table("knot_sync_cursors").upsert(
        {
            "external_user_id": external_user_id,
            "merchant_id": int(merchant_id),
            "cursor": cursor,
            "updated_at": _now_iso(),
        },
        on_conflict="external_user_id,merchant_id",
    ).execute()


def _upsert_transactions(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Upsert transaction rows on (provider, external_id).

    Returns (inserted_count, updated_count). Supabase doesn't expose the
    insert-vs-update breakdown directly, so we approximate by checking which
    external_ids already existed before the upsert.
    """
    if not rows:
        return 0, 0
    sb = get_supabase()
    external_ids = [r["external_id"] for r in rows if r.get("external_id")]
    existing: set[str] = set()
    if external_ids:
        existed_resp = (
            sb.table("transactions")
            .select("external_id")
            .eq("provider", "knot")
            .in_("external_id", external_ids)
            .execute()
        )
        for row in existed_resp.data or []:
            if isinstance(row, dict) and row.get("external_id"):
                existing.add(str(row["external_id"]))

    sb.table("transactions").upsert(rows, on_conflict="provider,external_id").execute()

    inserted = sum(1 for r in rows if str(r.get("external_id")) not in existing)
    updated = len(rows) - inserted
    return inserted, updated


def _ensure_account_row(
    *,
    company_id: str,
    external_user_id: str,
    merchant_id: int,
    merchant_name: Optional[str],
    status: str = "connected",
    last_session_id: Optional[str] = None,
    last_authenticated_at: Optional[str] = None,
    last_synced_at: Optional[str] = None,
    last_error: Optional[str] = None,
) -> dict[str, Any] | None:
    sb = get_supabase()
    payload: dict[str, Any] = {
        "company_id": company_id,
        "external_user_id": external_user_id,
        "merchant_id": int(merchant_id),
        "merchant_name": merchant_name,
        "connection_status": status,
        "updated_at": _now_iso(),
    }
    if last_session_id is not None:
        payload["last_session_id"] = last_session_id
    if last_authenticated_at is not None:
        payload["last_authenticated_at"] = last_authenticated_at
    if last_synced_at is not None:
        payload["last_synced_at"] = last_synced_at
    if last_error is not None:
        payload["last_error"] = last_error
    resp = sb.table("knot_merchant_accounts").upsert(
        payload, on_conflict="external_user_id,merchant_id"
    ).execute()
    rows = resp.data or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def get_or_create_merchant_account(
    *,
    company_id: str,
    external_user_id: str,
    merchant_id: int,
    merchant_name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any] | None:
    """Public helper used by the AUTHENTICATED webhook + manual link flow."""
    log.info(
        "account.upsert",
        company_id=company_id,
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        merchant_name=merchant_name,
    )
    return _ensure_account_row(
        company_id=company_id,
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        status="connected",
        last_session_id=session_id,
        last_authenticated_at=_now_iso(),
    )


# ── Sync log helpers ──────────────────────────────────────────────────────────


def _start_sync_log(
    *,
    company_id: str,
    external_user_id: str,
    merchant_id: int,
    trigger: str,
    cursor_before: Optional[str],
) -> Optional[str]:
    sb = get_supabase()
    resp = (
        sb.table("knot_sync_log")
        .insert(
            {
                "company_id": company_id,
                "external_user_id": external_user_id,
                "merchant_id": int(merchant_id),
                "trigger": trigger,
                "cursor_before": cursor_before,
                "status": "running",
                "started_at": _now_iso(),
            }
        )
        .execute()
    )
    rows = resp.data or []
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("id"))
    return None


def _finish_sync_log(
    sync_id: Optional[str],
    *,
    pages: int,
    inserted: int,
    updated: int,
    cursor_after: Optional[str],
    status: str,
    error: Optional[str] = None,
    duration_ms: int = 0,
) -> None:
    if not sync_id:
        return
    sb = get_supabase()
    sb.table("knot_sync_log").update(
        {
            "pages_fetched": int(pages),
            "inserted_count": int(inserted),
            "updated_count": int(updated),
            "cursor_after": cursor_after,
            "status": status,
            "error": error,
            "finished_at": _now_iso(),
            "duration_ms": int(duration_ms),
        }
    ).eq("id", sync_id).execute()


# ── Core sync loop ────────────────────────────────────────────────────────────


async def sync_merchant(
    *,
    external_user_id: str,
    merchant_id: int,
    merchant_name: Optional[str] = None,
    trigger: str = "manual",
    company_id: Optional[str] = None,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    client: Optional[KnotClient] = None,
) -> dict[str, Any]:
    """
    Sync transactions for one (external_user_id, merchant_id) pair.

    Loops until next_cursor is null. Persists cursor after every page.
    Always upserts. Always logs.
    """
    knot = client or get_knot_client()
    company_id = company_id or await asyncio.to_thread(_resolve_company_id, external_user_id)
    cursor_before = await asyncio.to_thread(_load_cursor, external_user_id, merchant_id)

    log.info(
        "sync.start",
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        trigger=trigger,
        company_id=company_id,
        cursor_present=cursor_before is not None,
    )

    sync_id = await asyncio.to_thread(
        _start_sync_log,
        company_id=company_id,
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        trigger=trigger,
        cursor_before=cursor_before,
    )

    started = time.time()
    cursor: Optional[str] = cursor_before
    pages = 0
    total_inserted = 0
    total_updated = 0
    resolved_merchant_name = merchant_name
    error_msg: Optional[str] = None

    try:
        while True:
            response = await knot.sync_transactions(
                external_user_id=external_user_id,
                merchant_id=merchant_id,
                cursor=cursor,
                limit=page_limit,
            )
            pages += 1
            merchant = response.get("merchant") or {}
            if isinstance(merchant, dict) and merchant.get("name"):
                resolved_merchant_name = str(merchant.get("name"))

            txns = response.get("transactions") or []
            log.info(
                "sync.page",
                external_user_id=external_user_id,
                merchant_id=merchant_id,
                page=pages,
                fetched=len(txns),
            )

            rows = []
            for raw in txns:
                if not isinstance(raw, dict):
                    continue
                try:
                    rows.append(
                        knot_to_transaction_row(
                            raw,
                            company_id=company_id,
                            external_user_id=external_user_id,
                            merchant_id=merchant_id,
                            merchant_name=resolved_merchant_name or "",
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warn("normalize.skip", error=str(exc), txn_id=raw.get("id"))

            if rows:
                inserted, updated = await asyncio.to_thread(_upsert_transactions, rows)
                total_inserted += inserted
                total_updated += updated
                log.info(
                    "sync.upsert",
                    page=pages,
                    inserted=inserted,
                    updated=updated,
                )

            next_cursor = response.get("next_cursor")
            cursor = next_cursor
            await asyncio.to_thread(_persist_cursor, external_user_id, merchant_id, cursor)

            if not cursor:
                break

        # mark account as connected + last_synced_at after a successful run
        await asyncio.to_thread(
            _ensure_account_row,
            company_id=company_id,
            external_user_id=external_user_id,
            merchant_id=merchant_id,
            merchant_name=resolved_merchant_name,
            status="connected",
            last_synced_at=_now_iso(),
            last_error=None,
        )

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        log.error(
            "sync.error",
            external_user_id=external_user_id,
            merchant_id=merchant_id,
            error=error_msg,
        )
        await asyncio.to_thread(
            _ensure_account_row,
            company_id=company_id,
            external_user_id=external_user_id,
            merchant_id=merchant_id,
            merchant_name=resolved_merchant_name,
            status="error",
            last_error=error_msg,
        )
    finally:
        duration_ms = int((time.time() - started) * 1000)
        await asyncio.to_thread(
            _finish_sync_log,
            sync_id,
            pages=pages,
            inserted=total_inserted,
            updated=total_updated,
            cursor_after=cursor,
            status=("error" if error_msg else "success"),
            error=error_msg,
            duration_ms=duration_ms,
        )

    log.info(
        "sync.done",
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        pages=pages,
        inserted=total_inserted,
        updated=total_updated,
        duration_ms=duration_ms,
        error=error_msg,
    )

    return {
        "ok": error_msg is None,
        "pages": pages,
        "inserted": total_inserted,
        "updated": total_updated,
        "cursor_after": cursor,
        "error": error_msg,
        "company_id": company_id,
        "external_user_id": external_user_id,
        "merchant_id": merchant_id,
        "merchant_name": resolved_merchant_name,
    }


# ── UPDATED_TRANSACTIONS_AVAILABLE handler ───────────────────────────────────


async def ingest_updated_transactions(
    *,
    external_user_id: str,
    merchant_id: int,
    transaction_ids: list[str],
    merchant_name: Optional[str] = None,
    client: Optional[KnotClient] = None,
) -> dict[str, Any]:
    """
    Fetch each updated transaction and upsert. Existing rows are mutated;
    no new INSERT events fire, so agents are not re-triggered.
    """
    if not transaction_ids:
        return {"ok": True, "updated": 0}
    knot = client or get_knot_client()
    company_id = await asyncio.to_thread(_resolve_company_id, external_user_id)

    log.info(
        "updates.start",
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        count=len(transaction_ids),
    )

    rows: list[dict[str, Any]] = []
    for tid in transaction_ids:
        try:
            txn = await knot.get_transaction(str(tid))
        except Exception as exc:  # noqa: BLE001
            log.warn("updates.fetch_error", transaction_id=tid, error=str(exc))
            continue
        if not isinstance(txn, dict) or not txn.get("id"):
            continue
        try:
            rows.append(
                knot_to_transaction_row(
                    txn,
                    company_id=company_id,
                    external_user_id=external_user_id,
                    merchant_id=merchant_id,
                    merchant_name=merchant_name or "",
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warn("updates.normalize_error", transaction_id=tid, error=str(exc))

    inserted = updated = 0
    if rows:
        inserted, updated = await asyncio.to_thread(_upsert_transactions, rows)
    log.info(
        "updates.done",
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        inserted=inserted,
        updated=updated,
    )
    return {"ok": True, "inserted": inserted, "updated": updated}
