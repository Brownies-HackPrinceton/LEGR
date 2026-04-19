"""
FastAPI endpoints for the Knot integration.

Frontend-facing:
  GET  /knot/health                  — env wiring + connectivity ping
  GET  /knot/config                  — public config the web SDK needs
  GET  /knot/merchants               — list available merchants for the platform
  POST /knot/session                 — create a Knot session for the SDK
  GET  /knot/accounts                — linked merchant accounts for the company
  POST /knot/sync                    — manual sync for one merchant
  POST /knot/dev/simulate-link       — dev-only: simulate link + emit webhooks
  GET  /knot/sync/log                — recent sync runs (observability)
  GET  /knot/webhook/events          — recent webhook events (observability)

Knot-facing:
  POST /webhooks/knot                — webhook receiver (returns 200 fast)

All side effects are logged to stdout via `log` so the operator can watch
the backend terminal in real time.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from supabase_client import get_supabase

from . import log
from .client import (
    KnotAPIError,
    KnotConfigError,
    get_knot_client,
    log_env_check,
    verify_webhook_signature,
)
from .ingest import (
    DEFAULT_COMPANY_ID,
    get_or_create_merchant_account,
    ingest_updated_transactions,
    sync_merchant,
)

router = APIRouter(tags=["knot"])


def _company_id(default: Optional[str] = None) -> str:
    return default or os.getenv("FLUX_COMPANY_ID", DEFAULT_COMPANY_ID)


def _external_user_id(company_id: str) -> str:
    """Stable Knot external_user_id derived from the Flux company id.

    Falls back to ``company:<id>`` if Supabase is unreachable or the row
    doesn't have the column populated (pre-migration deployments).
    """
    try:
        sb = get_supabase()
        resp = (
            sb.table("companies")
            .select("knot_external_user_id")
            .eq("id", company_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows and isinstance(rows[0], dict) and rows[0].get("knot_external_user_id"):
            return str(rows[0]["knot_external_user_id"])
    except Exception as exc:  # noqa: BLE001 — never block /knot/config on supabase
        log.warn("external_user_id.fallback", error=str(exc))
    return f"company:{company_id}"


# ── Health + config ───────────────────────────────────────────────────────────


@router.get("/knot/health")
async def knot_health() -> dict[str, Any]:
    state = log_env_check()
    reachable = False
    error: Optional[str] = None
    try:
        knot = get_knot_client()
        merchants = await knot.list_merchants(type="transaction_link", platform="web")
        reachable = isinstance(merchants, list)
        log.info("health.ok", merchants=len(merchants))
    except KnotConfigError as exc:
        error = str(exc)
        log.warn("health.config_error", error=error)
    except KnotAPIError as exc:
        error = f"{exc.status}: {exc.body!r}"
        log.warn("health.api_error", error=error)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        log.warn("health.unexpected_error", error=error)
    return {"ok": reachable and not error, "env": state, "error": error}


@router.get("/knot/config")
async def knot_config() -> dict[str, Any]:
    """
    Public config the frontend needs to open the Knot Web SDK.
    Returns ONLY the client_id + environment — never the secret.
    """
    return {
        "client_id": os.getenv("KNOT_CLIENT_ID") or None,
        "environment": (os.getenv("KNOT_ENVIRONMENT") or "development"),
        "external_user_id": _external_user_id(_company_id()),
        "company_id": _company_id(),
    }


# ── Merchant catalog ──────────────────────────────────────────────────────────


@router.get("/knot/merchants")
async def list_merchants(
    platform: str = Query("web"),
    type: str = Query("transaction_link"),
) -> dict[str, Any]:
    try:
        merchants = await get_knot_client().list_merchants(type=type, platform=platform)
    except KnotConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except KnotAPIError as exc:
        raise HTTPException(status_code=502, detail={"status": exc.status, "body": exc.body})
    return {"merchants": merchants}


# ── Session create ────────────────────────────────────────────────────────────


@router.post("/knot/session")
async def create_session(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    company_id = _company_id(payload.get("company_id"))
    external_user_id = payload.get("external_user_id") or _external_user_id(company_id)
    type_ = payload.get("type", "transaction_link")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    email = payload.get("email") if isinstance(payload.get("email"), str) else None
    phone_number = payload.get("phone_number") if isinstance(payload.get("phone_number"), str) else None
    log.info(
        "session.create",
        external_user_id=external_user_id,
        company_id=company_id,
        type=type_,
        has_metadata=bool(metadata),
    )
    try:
        data = await get_knot_client().create_session(
            external_user_id=external_user_id,
            type=type_,
            metadata=metadata,
            email=email,
            phone_number=phone_number,
        )
    except KnotConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except KnotAPIError as exc:
        log.error("session.create_failed", status=exc.status, body=str(exc.body))
        raise HTTPException(status_code=502, detail={"status": exc.status, "body": exc.body})
    return {
        "session": data.get("session"),
        "external_user_id": external_user_id,
        "company_id": company_id,
        "environment": (os.getenv("KNOT_ENVIRONMENT") or "development"),
        "client_id": os.getenv("KNOT_CLIENT_ID") or None,
    }


# ── Linked accounts ───────────────────────────────────────────────────────────


@router.get("/knot/accounts")
async def linked_accounts(company_id: Optional[str] = None) -> dict[str, Any]:
    cid = _company_id(company_id)
    sb = get_supabase()
    resp = (
        sb.table("knot_merchant_accounts")
        .select("*")
        .eq("company_id", cid)
        .order("updated_at", desc=True)
        .execute()
    )
    return {"company_id": cid, "accounts": resp.data or []}


# ── Manual sync ───────────────────────────────────────────────────────────────


@router.post("/knot/sync")
async def trigger_sync(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    company_id = _company_id(payload.get("company_id"))
    merchant_id = payload.get("merchant_id")
    if not merchant_id:
        raise HTTPException(status_code=400, detail="merchant_id is required")
    try:
        merchant_id = int(merchant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="merchant_id must be an integer")
    external_user_id = payload.get("external_user_id") or _external_user_id(company_id)
    merchant_name = payload.get("merchant_name")
    trigger = str(payload.get("trigger") or "manual")

    result = await sync_merchant(
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        trigger=trigger,
        company_id=company_id,
    )
    return result


# ── Dev-only simulate-link ───────────────────────────────────────────────────


@router.post("/knot/dev/simulate-link")
async def dev_simulate_link(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    company_id = _company_id(payload.get("company_id"))
    merchant_id = payload.get("merchant_id")
    if not merchant_id:
        raise HTTPException(status_code=400, detail="merchant_id is required")
    try:
        merchant_id = int(merchant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="merchant_id must be an integer")

    external_user_id = payload.get("external_user_id") or _external_user_id(company_id)
    merchant_name = payload.get("merchant_name")
    new = bool(payload.get("new", True))
    updated = bool(payload.get("updated", False))

    # Optimistically mark the account as connected so the UI updates immediately.
    await asyncio.to_thread(
        get_or_create_merchant_account,
        company_id=company_id,
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        merchant_name=merchant_name,
    )

    try:
        sim = await get_knot_client().dev_simulate_link(
            external_user_id=external_user_id,
            merchant_id=merchant_id,
            new=new,
            updated=updated,
        )
    except KnotConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except KnotAPIError as exc:
        raise HTTPException(status_code=502, detail={"status": exc.status, "body": exc.body})

    return {
        "ok": True,
        "external_user_id": external_user_id,
        "merchant_id": merchant_id,
        "knot_response": sim,
        "note": (
            "Knot will deliver AUTHENTICATED + NEW_TRANSACTIONS_AVAILABLE webhooks "
            "to your KNOT_PUBLIC_WEBHOOK_URL (or you can call POST /knot/sync directly)."
        ),
    }


# ── Observability ─────────────────────────────────────────────────────────────


@router.get("/knot/sync/log")
async def sync_log(company_id: Optional[str] = None, limit: int = 25) -> dict[str, Any]:
    cid = _company_id(company_id)
    resp = (
        get_supabase()
        .table("knot_sync_log")
        .select("*")
        .eq("company_id", cid)
        .order("started_at", desc=True)
        .limit(min(int(limit), 200))
        .execute()
    )
    return {"company_id": cid, "log": resp.data or []}


@router.get("/knot/webhook/events")
async def webhook_events(limit: int = 25) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("knot_webhook_events")
        .select("*")
        .order("received_at", desc=True)
        .limit(min(int(limit), 200))
        .execute()
    )
    return {"events": resp.data or []}


# ── Webhook receiver ──────────────────────────────────────────────────────────


def _record_webhook(payload: dict[str, Any]) -> Optional[str]:
    sb = get_supabase()
    merchant = payload.get("merchant") or {}
    _mid = (merchant.get("id") if isinstance(merchant, dict) else None) or payload.get("merchant_id")
    _mname = (merchant.get("name") if isinstance(merchant, dict) else None) or payload.get("merchant_name")
    row = {
        "event": str(payload.get("event") or "UNKNOWN"),
        "external_user_id": payload.get("external_user_id"),
        "merchant_id": (int(_mid) if _mid is not None else None),
        "merchant_name": _mname,
        "session_id": payload.get("session_id"),
        "task_id": (str(payload.get("task_id")) if payload.get("task_id") is not None else None),
        "payload": payload,
        "status": "received",
    }
    resp = sb.table("knot_webhook_events").insert(row).execute()
    rows = resp.data or []
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("id"))
    return None


def _mark_webhook_done(event_id: Optional[str], status: str, error: Optional[str] = None) -> None:
    if not event_id:
        return
    from datetime import datetime, timezone
    get_supabase().table("knot_webhook_events").update(
        {
            "status": status,
            "error": error,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", event_id).execute()


async def _process_webhook(event_id: Optional[str], payload: dict[str, Any]) -> None:
    """Run the actual side-effect work for a webhook event (background)."""
    event = str(payload.get("event") or "").upper()
    external_user_id = str(payload.get("external_user_id") or "")

    # Knot sends merchant info either as a nested ``merchant: {id, name}`` object
    # (older webhook spec) or as flat top-level ``merchant_id`` / ``merchant_name``
    # fields (newer / production spec). Check both.
    merchant = payload.get("merchant") or {}
    _mid_nested = merchant.get("id") if isinstance(merchant, dict) else None
    _mid_flat = payload.get("merchant_id")
    merchant_id = _mid_nested if _mid_nested is not None else (_mid_flat if _mid_flat is not None else None)
    if merchant_id is not None:
        try:
            merchant_id = int(merchant_id)
        except (TypeError, ValueError):
            merchant_id = None

    _mname_nested = merchant.get("name") if isinstance(merchant, dict) else None
    merchant_name = _mname_nested or payload.get("merchant_name")

    log.info(
        "webhook.processing",
        event=event,
        external_user_id=external_user_id,
        merchant_id=merchant_id,
        merchant_name=merchant_name,
    )

    try:
        if event == "AUTHENTICATED":
            if external_user_id and merchant_id is not None:
                from .ingest import _resolve_company_id  # local import: avoid cycle
                company_id = await asyncio.to_thread(_resolve_company_id, external_user_id)
                await asyncio.to_thread(
                    get_or_create_merchant_account,
                    company_id=company_id,
                    external_user_id=external_user_id,
                    merchant_id=int(merchant_id),
                    merchant_name=merchant_name,
                    session_id=payload.get("session_id"),
                )
                log.info(
                    "webhook.authenticated.persisted",
                    external_user_id=external_user_id,
                    merchant_id=merchant_id,
                )

        elif event == "NEW_TRANSACTIONS_AVAILABLE":
            if external_user_id and merchant_id is not None:
                await sync_merchant(
                    external_user_id=external_user_id,
                    merchant_id=int(merchant_id),
                    merchant_name=merchant_name,
                    trigger="webhook",
                )

        elif event == "UPDATED_TRANSACTIONS_AVAILABLE":
            # Knot's webhook body wraps event-specific fields under `data`, but
            # historical/simulated payloads have also used top-level keys, so we
            # look in multiple places and accept both `[{id: ...}]` and `[uuid, ...]`.
            raw_list: Any = None
            for key in ("updated", "transactions", "transaction_ids"):
                data_obj = payload.get("data") or {}
                if isinstance(data_obj, dict) and data_obj.get(key):
                    raw_list = data_obj.get(key)
                    break
                if payload.get(key):
                    raw_list = payload.get(key)
                    break
            ids: list[str] = []
            if isinstance(raw_list, list):
                for entry in raw_list:
                    if isinstance(entry, str) and entry:
                        ids.append(entry)
                    elif isinstance(entry, dict) and entry.get("id"):
                        ids.append(str(entry["id"]))
            if external_user_id and merchant_id is not None and ids:
                log.info("webhook.updated_transactions.extracted", count=len(ids))
                await ingest_updated_transactions(
                    external_user_id=external_user_id,
                    merchant_id=int(merchant_id),
                    transaction_ids=ids,
                    merchant_name=merchant_name,
                )
            else:
                log.warn("webhook.updated_transactions.no_ids", payload_keys=list(payload.keys()))

        elif event == "ACCOUNT_LOGIN_REQUIRED":
            if external_user_id and merchant_id is not None:
                from .ingest import _resolve_company_id
                company_id = await asyncio.to_thread(_resolve_company_id, external_user_id)
                await asyncio.to_thread(
                    get_or_create_merchant_account,
                    company_id=company_id,
                    external_user_id=external_user_id,
                    merchant_id=int(merchant_id),
                    merchant_name=merchant_name,
                )
                # Mark disconnected after upsert.
                get_supabase().table("knot_merchant_accounts").update(
                    {"connection_status": "disconnected"}
                ).eq("external_user_id", external_user_id).eq(
                    "merchant_id", int(merchant_id)
                ).execute()
                log.warn(
                    "webhook.account_login_required",
                    external_user_id=external_user_id,
                    merchant_id=merchant_id,
                )

        elif event == "MERCHANT_STATUS_UPDATE":
            log.info("webhook.merchant_status_update", payload=payload)

        else:
            log.warn("webhook.unhandled_event", event=event)

        await asyncio.to_thread(_mark_webhook_done, event_id, "done", None)
    except Exception as exc:  # noqa: BLE001
        log.error("webhook.processing_failed", event=event, error=str(exc))
        await asyncio.to_thread(_mark_webhook_done, event_id, "error", str(exc))


@router.post("/webhooks/knot")
async def knot_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Knot retries on non-200 responses (10s timeout, up to 2 retries).
    We persist the event and 200 immediately, then run side effects in the
    background. If ``KNOT_VERIFY_WEBHOOKS=1`` we also HMAC-verify the
    ``Knot-Signature`` header per
    https://docs.knotapi.com/webhooks#webhook-verification.
    """
    try:
        payload = await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8", "replace")
        log.warn("webhook.invalid_json", raw=raw[:512])
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=200)

    if not isinstance(payload, dict):
        log.warn("webhook.invalid_payload_type", type=str(type(payload)))
        return JSONResponse({"ok": False, "error": "invalid_payload"}, status_code=200)

    verify_flag = (os.getenv("KNOT_VERIFY_WEBHOOKS") or "0").lower() in ("1", "true", "yes")
    if verify_flag:
        header_map = {k.lower(): v for k, v in request.headers.items()}
        ok, reason = verify_webhook_signature(
            headers=header_map,
            body_fields={
                "event": payload.get("event"),
                "session_id": payload.get("session_id"),
            },
        )
        if ok:
            log.info("webhook.signature_ok", event=payload.get("event"))
        else:
            log.warn("webhook.signature_failed", event=payload.get("event"), reason=reason)
            return JSONResponse({"ok": False, "error": "signature_invalid"}, status_code=401)

    event_id: Optional[str] = None
    try:
        event_id = await asyncio.to_thread(_record_webhook, payload)
    except Exception as exc:  # noqa: BLE001
        log.error("webhook.persist_failed", error=str(exc))

    log.info(
        "webhook.received",
        event=payload.get("event"),
        external_user_id=payload.get("external_user_id"),
        event_id=event_id,
    )

    background_tasks.add_task(_process_webhook, event_id, payload)
    return {"ok": True, "event_id": event_id}
