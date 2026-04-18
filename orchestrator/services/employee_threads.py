"""
Employee threads — per-employee iMessage conversations for expense clarification.

The founder never sees these unless an escalation is needed. Questions are sent
to the employee's phone; replies are matched back by phone number and
the thread state is advanced.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from supabase_client import get_supabase
from services.imessage_sender import send_to_employee


# ── DB helpers ────────────────────────────────────────────────────────────────

def _fetch_employee_by_phone(phone: str) -> Optional[dict[str, Any]]:
    resp = (
        get_supabase()
        .table("employees")
        .select("*")
        .eq("phone", phone)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _open_thread(
    company_id: str,
    employee_id: str,
    transaction_id: Optional[str],
    question: str,
) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("employee_threads")
        .insert({
            "company_id": company_id,
            "employee_id": employee_id,
            "transaction_id": transaction_id,
            "state": "awaiting_reply",
            "question": question,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else {}


def _find_open_thread(employee_id: str) -> Optional[dict[str, Any]]:
    resp = (
        get_supabase()
        .table("employee_threads")
        .select("*")
        .eq("employee_id", employee_id)
        .eq("state", "awaiting_reply")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _close_thread(thread_id: str, response: str) -> None:
    get_supabase().table("employee_threads").update({
        "state": "resolved",
        "employee_response": response,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", thread_id).execute()


def _escalate_thread(thread_id: str, reason: str) -> None:
    get_supabase().table("employee_threads").update({
        "state": "escalated",
        "escalated_to_founder": True,
        "escalation_reason": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", thread_id).execute()


# ── Public API ────────────────────────────────────────────────────────────────

async def ask_employee(
    company_id: str,
    employee_id: str,
    phone: str,
    merchant: str,
    amount: float,
    transaction_id: Optional[str] = None,
) -> bool:
    """Open an employee thread and send a clarification question."""
    question = (
        f"Hi — I saw a ${amount:g} charge at {merchant} on your card. "
        f"What was this for? (one-line reply)"
    )

    def _open() -> dict:
        return _open_thread(company_id, employee_id, transaction_id, question)

    await asyncio.to_thread(_open)
    return await send_to_employee(phone, question)


async def handle_employee_reply(
    phone: str,
    reply_text: str,
) -> dict[str, Any]:
    """
    Called when an employee messages the bridge phone.
    Returns action dict for main.py (may include founder escalation).
    """
    employee = await asyncio.to_thread(_fetch_employee_by_phone, phone)
    if not employee:
        return {"status": "unknown_employee", "phone": phone}

    thread = await asyncio.to_thread(_find_open_thread, employee["id"])
    if not thread:
        return {"status": "no_open_thread", "employee": employee.get("name")}

    low = reply_text.lower()
    # Simple escalation triggers
    needs_escalation = any(w in low for w in ("don't know", "not mine", "wasn't me", "fraud", "stolen"))

    await asyncio.to_thread(_close_thread, thread["id"], reply_text)

    if needs_escalation:
        await asyncio.to_thread(_escalate_thread, thread["id"], f"Employee flagged: {reply_text[:100]}")
        return {
            "status": "escalated",
            "employee": employee.get("name"),
            "reply": reply_text,
            "transaction_id": thread.get("transaction_id"),
            "message": (
                f"🚨 {employee.get('name')} flagged a charge as suspicious: \"{reply_text}\". "
                f"Review and escalate?"
            ),
            "requires_founder": True,
        }

    return {
        "status": "resolved",
        "employee": employee.get("name"),
        "reply": reply_text,
        "transaction_id": thread.get("transaction_id"),
    }
