from __future__ import annotations

import asyncio
from typing import Any

from supabase_client import get_supabase

_POLICY_RED_FLAG_KEYWORDS = ("strip", "casino", "liquor")


def _fetch_employee_row(employee_id: str) -> dict[str, Any]:
    supabase = get_supabase()
    resp = supabase.table("employees").select("*").eq("id", employee_id).limit(1).execute()
    rows = resp.data or []
    if not rows:
        raise ValueError(f"No employee found for id {employee_id}")
    row = rows[0]
    if not isinstance(row, dict):
        raise TypeError("Unexpected employee row shape from Supabase")
    return row


async def compliance_agent(merchant: str, amount: float, employee_id: str, memo: str) -> dict[str, Any]:
    """Scores an employee card swipe against company policy. Returns approval decision."""
    emp = await asyncio.to_thread(_fetch_employee_row, employee_id)

    cap_raw = emp.get("monthly_expense_cap")
    cap = float(cap_raw) if cap_raw is not None else 0.0

    flags: list[str] = []
    if amount > cap:
        flags.append(f"exceeds ${cap:g} cap")
    if memo is None or not str(memo).strip():
        flags.append("no memo provided")

    merchant_lower = (merchant or "").lower()
    if any(x in merchant_lower for x in _POLICY_RED_FLAG_KEYWORDS):
        flags.append("policy red flag")

    approved = len(flags) == 0
    confidence = 0.95 if approved else 0.3

    name = str(emp.get("name") or "Unknown")

    return {
        "approved": approved,
        "confidence": confidence,
        "flags": flags,
        "employee": name,
        "message": f"{'✓ Auto-approved' if approved else '✗ FLAGGED'}: {name} ${amount:g} at {merchant}",
    }
