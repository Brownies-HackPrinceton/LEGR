"""
Negotiation state machine.

States:  pending → draft_sent → waiting_reply → counter_received
         → counter_sent → closed_won | closed_lost | stalled

State persists to both Supabase (negotiation_threads) and a local JSON file
so it survives orchestrator restarts.

Public API:
  start_negotiation(...)  → creates thread, returns draft email
  send_initial(thread_id) → transitions to draft_sent
  handle_vendor_reply(thread_id, reply_text) → classify + draft counter
  get_status(thread_id)   → current state snapshot
  maybe_stall(...)        → called periodically; stalls threads with no reply > 5 days
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from dedalus_labs import AsyncDedalus, DedalusRunner

from flux_persona import FLUX_PERSONA
from supabase_client import get_supabase

NegState = Literal[
    "pending", "draft_sent", "waiting_reply",
    "counter_received", "counter_sent",
    "closed_won", "closed_lost", "stalled",
]

_STATE_DIR = Path(os.getenv("NEGOTIATION_STATE_DIR", "/tmp/flux_negotiations"))
_STALL_DAYS = 5


def _state_path(thread_id: str) -> Path:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    return _STATE_DIR / f"{thread_id}.json"


def _write_disk(thread_id: str, data: dict[str, Any]) -> None:
    _state_path(thread_id).write_text(json.dumps(data, default=str))


def _read_disk(thread_id: str) -> Optional[dict[str, Any]]:
    p = _state_path(thread_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _db_create(data: dict[str, Any]) -> dict[str, Any]:
    resp = get_supabase().table("negotiation_threads").insert(data).execute()
    rows = resp.data or []
    return rows[0] if rows else data


def _db_update(thread_id: str, patch: dict[str, Any]) -> None:
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    get_supabase().table("negotiation_threads").update(patch).eq("id", thread_id).execute()


def _db_fetch(thread_id: str) -> Optional[dict[str, Any]]:
    resp = (
        get_supabase()
        .table("negotiation_threads")
        .select("*")
        .eq("id", thread_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


# ── LLM helpers ───────────────────────────────────────────────────────────────

async def _draft_counter(
    vendor: str,
    original_price: float,
    target_pct: float,
    vendor_offer_pct: float,
    floor_pct: float,
    vendor_reply: str,
) -> tuple[str, bool]:
    """Return (counter_email_text, below_floor)."""
    below = vendor_offer_pct < floor_pct
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        # Minimal fallback
        ask = max(target_pct, (vendor_offer_pct + target_pct) / 2)
        text = (
            f"Hi {vendor} team,\n\nThank you for the {vendor_offer_pct}% offer. "
            f"We need to reach {ask:.0f}% to commit. Can you make that work?\n\nThanks"
        )
        return text, below

    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    prompt = f"""
You are drafting a counter-offer reply to {vendor}'s renewal email.

Vendor offered: {vendor_offer_pct}% discount
Our target: {target_pct}% discount
Our policy floor (minimum we accept): {floor_pct}%
Their reply: {vendor_reply}

Draft a 2-paragraph reply. Push for our target. Be firm but professional.
If their offer is already at or above our target, accept gracefully.
"""
    try:
        resp = await runner.run(
            input=prompt,
            model="anthropic/claude-sonnet-4-6",
            max_tokens=400,
            instructions=FLUX_PERSONA,
        )
        return (resp.final_output or "").strip(), below
    except Exception:
        ask = max(target_pct, (vendor_offer_pct + target_pct) / 2)
        return (
            f"Hi {vendor} team,\nThank you. We need {ask:.0f}% to proceed. Please confirm.\n\nThanks",
            below,
        )


async def _classify_reply(reply_text: str) -> dict[str, Any]:
    """Extract: offer_pct (float|None), accepted (bool), declined (bool)."""
    import re
    # Simple heuristics first
    low = reply_text.lower()
    declined = any(w in low for w in ("unable", "cannot", "won't", "can't offer", "no discount", "best price"))
    # Look for a percentage number
    pcts = re.findall(r"\b(\d{1,2})%", reply_text)
    offer_pct = float(pcts[0]) if pcts else None
    accepted = offer_pct is not None and any(w in low for w in ("confirm", "agreed", "done", "proceed", "accept"))
    return {"offer_pct": offer_pct, "accepted": accepted, "declined": declined}


# ── Public API ────────────────────────────────────────────────────────────────

async def start_negotiation(
    company_id: str,
    vendor: str,
    original_price: float,
    target_pct: float,
    draft_email: str,
    floor_pct: float = 5.0,
) -> dict[str, Any]:
    row = {
        "company_id": company_id,
        "vendor": vendor,
        "state": "pending",
        "original_price": original_price,
        "target_discount_pct": target_pct,
        "policy_floor_pct": floor_pct,
        "draft_email": draft_email,
        "turn_count": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    created = await asyncio.to_thread(_db_create, row)
    thread_id = created.get("id", "local")
    await asyncio.to_thread(_write_disk, thread_id, created)
    return created


async def send_initial(thread_id: str) -> bool:
    """Mark draft as sent (caller is responsible for actually sending the email)."""
    patch = {
        "state": "waiting_reply",
        "next_action_at": (datetime.now(timezone.utc) + timedelta(days=_STALL_DAYS)).isoformat(),
    }
    await asyncio.to_thread(_db_update, thread_id, patch)
    disk = _read_disk(thread_id) or {}
    disk.update(patch)
    await asyncio.to_thread(_write_disk, thread_id, disk)
    return True


async def handle_vendor_reply(
    thread_id: str,
    reply_text: str,
) -> dict[str, Any]:
    """Process a vendor reply. Returns next-action dict for the orchestrator."""
    thread = await asyncio.to_thread(_db_fetch, thread_id) or _read_disk(thread_id) or {}

    classification = await _classify_reply(reply_text)
    offer_pct = classification.get("offer_pct")
    accepted = classification.get("accepted", False)
    declined = classification.get("declined", False)

    target_pct = float(thread.get("target_discount_pct") or 10.0)
    floor_pct = float(thread.get("policy_floor_pct") or 5.0)
    original_price = float(thread.get("original_price") or 0)
    turn_count = int(thread.get("turn_count") or 0) + 1
    vendor = thread.get("vendor", "vendor")

    if accepted or (offer_pct is not None and offer_pct >= target_pct):
        new_price = original_price * (1 - (offer_pct or target_pct) / 100)
        patch = {
            "state": "closed_won",
            "current_offer_pct": offer_pct,
            "latest_vendor_reply": reply_text[:500],
            "turn_count": turn_count,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "outcome_notes": f"Won at {offer_pct}%. New price: ${new_price:,.0f}/mo.",
        }
        await asyncio.to_thread(_db_update, thread_id, patch)
        return {
            "state": "closed_won",
            "message": (
                f"✅ {vendor} accepted {offer_pct}% discount. "
                f"New price: ${new_price:,.0f}/mo. Saved ${original_price - new_price:,.0f}/mo."
            ),
            "requires_founder": False,
        }

    if declined:
        patch = {
            "state": "closed_lost",
            "latest_vendor_reply": reply_text[:500],
            "turn_count": turn_count,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "outcome_notes": "Vendor declined discount request.",
        }
        await asyncio.to_thread(_db_update, thread_id, patch)
        return {
            "state": "closed_lost",
            "message": f"{vendor} declined. Want to escalate or cancel the subscription?",
            "requires_founder": True,
        }

    # Vendor made a counter offer
    counter_email, below_floor = await _draft_counter(
        vendor, original_price, target_pct,
        offer_pct or 0, floor_pct, reply_text,
    )
    patch = {
        "state": "counter_received",
        "current_offer_pct": offer_pct,
        "latest_vendor_reply": reply_text[:500],
        "turn_count": turn_count,
        "draft_email": counter_email,
        "next_action_at": (datetime.now(timezone.utc) + timedelta(days=_STALL_DAYS)).isoformat(),
    }
    await asyncio.to_thread(_db_update, thread_id, patch)

    if below_floor:
        return {
            "state": "counter_received",
            "below_policy_floor": True,
            "offer_pct": offer_pct,
            "message": (
                f"🚨 {vendor} came back at {offer_pct}% — below your {floor_pct}% floor. "
                f"Push back or walk away?"
            ),
            "draft_counter": counter_email,
            "requires_founder": True,
        }

    return {
        "state": "counter_received",
        "offer_pct": offer_pct,
        "message": (
            f"{vendor} offered {offer_pct}%. I pushed back citing competitive quotes. "
            f"Waiting on their response."
        ),
        "draft_counter": counter_email,
        "requires_founder": False,
    }


async def get_status(thread_id: str) -> Optional[dict[str, Any]]:
    return await asyncio.to_thread(_db_fetch, thread_id)


async def maybe_stall(company_id: str) -> list[dict[str, Any]]:
    """Check all waiting threads; mark stalled if no reply in STALL_DAYS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_STALL_DAYS)).isoformat()

    def _fetch_waiting() -> list[dict]:
        resp = (
            get_supabase()
            .table("negotiation_threads")
            .select("*")
            .eq("company_id", company_id)
            .in_("state", ["waiting_reply", "counter_sent"])
            .lte("next_action_at", datetime.now(timezone.utc).isoformat())
            .execute()
        )
        return list(resp.data or [])

    stalled = []
    threads = await asyncio.to_thread(_fetch_waiting)
    for t in threads:
        patch = {"state": "stalled", "outcome_notes": f"No reply after {_STALL_DAYS} days."}
        await asyncio.to_thread(_db_update, t["id"], patch)
        stalled.append({**t, **patch, "message": f"{t['vendor']} negotiation stalled — no reply in {_STALL_DAYS} days. Cancel or re-ping?"})
    return stalled
