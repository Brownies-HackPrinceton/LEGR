"""
Policy engine — evaluates per-company rules and fires autonomous actions
when conditions are met. All actions are logged to policy_actions.

Default policies (seeded in migration 006):
  auto_cancel          – cancel subs under $N/mo with 0 usage in X days
  auto_accept_discount – accept renewal discounts ≥ P% on contracts < $N
  auto_approve_expense – approve expenses matching prior-approved patterns
  production_infra     – block autonomous action on infra vendors
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase_client import get_supabase


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_policies(company_id: str) -> list[dict[str, Any]]:
    resp = (
        get_supabase()
        .table("policies")
        .select("*")
        .eq("company_id", company_id)
        .eq("enabled", True)
        .execute()
    )
    return list(resp.data or [])


def _by_type(policies: list[dict], t: str) -> Optional[dict[str, Any]]:
    return next((p for p in policies if p.get("type") == t), None)


def _log_action(
    company_id: str,
    policy_id: Optional[str],
    transaction_id: Optional[str],
    action_type: str,
    entity_name: str,
    amount: float,
    rationale: str,
) -> None:
    get_supabase().table("policy_actions").insert({
        "company_id": company_id,
        "policy_id": policy_id,
        "transaction_id": transaction_id,
        "action_type": action_type,
        "entity_name": entity_name,
        "amount": amount,
        "rationale": rationale,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# ── Production-infra guard ────────────────────────────────────────────────────

async def is_production_infra(company_id: str, vendor: str) -> bool:
    policies = await asyncio.to_thread(_fetch_policies, company_id)
    p = _by_type(policies, "production_infra")
    if not p:
        return False
    infra = [v.lower() for v in (p.get("production_infra_list") or [])]
    vl = vendor.lower()
    return any(vl in i or i in vl for i in infra)


# ── Auto-cancel ───────────────────────────────────────────────────────────────

async def evaluate_auto_cancel(
    company_id: str,
    vendor: str,
    monthly_cost: float,
    transaction_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Returns an autonomous-action dict if auto-cancel should fire, else None."""
    if await is_production_infra(company_id, vendor):
        return None

    policies = await asyncio.to_thread(_fetch_policies, company_id)
    p = _by_type(policies, "auto_cancel")
    if not p:
        return None

    cap = float(p.get("threshold_amount") or 100)
    days = int(p.get("threshold_days") or 60)

    if monthly_cost > cap:
        return None

    # Check seat_usage for any recent activity
    def _has_usage() -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        resp = (
            get_supabase()
            .table("seat_usage")
            .select("id")
            .eq("company_id", company_id)
            .ilike("tool", f"%{vendor.split()[0]}%")
            .gte("last_active_date", cutoff)
            .limit(1)
            .execute()
        )
        return bool(resp.data)

    if await asyncio.to_thread(_has_usage):
        return None

    rationale = (
        f"Auto-cancel: {vendor} at ${monthly_cost:g}/mo — "
        f"no seat activity in {days} days (threshold: <${cap:g}/mo)."
    )
    await asyncio.to_thread(
        _log_action,
        company_id, p.get("id"), transaction_id,
        "auto_cancel", vendor, monthly_cost, rationale,
    )
    return {
        "autonomous": True,
        "action": "cancel",
        "vendor": vendor,
        "monthly_savings": monthly_cost,
        "rationale": rationale,
        "undo_available": True,
        "message": (
            f"Canceled {vendor} — 0 usage in {days} days matched your auto-cancel policy. "
            f"Saved ${monthly_cost:g}/mo. Undo?"
        ),
    }


# ── Auto-accept discount ──────────────────────────────────────────────────────

async def evaluate_auto_accept_discount(
    company_id: str,
    vendor: str,
    current_price: float,
    offered_pct: float,
) -> Optional[dict[str, Any]]:
    if await is_production_infra(company_id, vendor):
        return None

    policies = await asyncio.to_thread(_fetch_policies, company_id)
    p = _by_type(policies, "auto_accept_discount")
    if not p:
        return None

    cap = float(p.get("threshold_amount") or 5000)
    min_pct = float(p.get("threshold_discount_pct") or 10.0)

    if current_price > cap or offered_pct < min_pct:
        return None

    new_price = current_price * (1 - offered_pct / 100)
    rationale = (
        f"Auto-accepted {vendor} at {offered_pct}% discount "
        f"(≥{min_pct}% rule, ${current_price:g}/mo < ${cap:g} cap). "
        f"New monthly: ${new_price:,.0f}."
    )
    await asyncio.to_thread(
        _log_action,
        company_id, p.get("id"), None,
        "auto_accept_discount", vendor, current_price, rationale,
    )
    return {
        "autonomous": True,
        "action": "accept_renewal",
        "vendor": vendor,
        "discount_pct": offered_pct,
        "new_monthly": new_price,
        "rationale": rationale,
        "message": (
            f"Auto-renewed {vendor} at {offered_pct}% discount "
            f"(${new_price:,.0f}/mo). Matched your auto-accept policy."
        ),
    }


# ── Auto-approve expense ──────────────────────────────────────────────────────

async def evaluate_auto_approve_expense(
    company_id: str,
    employee_id: str,
    merchant: str,
    amount: float,
    transaction_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if await is_production_infra(company_id, merchant):
        return None

    policies = await asyncio.to_thread(_fetch_policies, company_id)
    p = _by_type(policies, "auto_approve_expense")
    if not p:
        return None

    cap = float(p.get("threshold_amount") or 200)
    if amount > cap:
        return None

    # Check if same employee + same merchant was previously approved
    def _prior_approved() -> bool:
        resp = (
            get_supabase()
            .table("transactions")
            .select("id")
            .eq("company_id", company_id)
            .eq("employee_id", employee_id)
            .ilike("merchant", f"%{merchant.split()[0]}%")
            .eq("founder_action", "Y")
            .limit(1)
            .execute()
        )
        return bool(resp.data)

    if not await asyncio.to_thread(_prior_approved):
        return None

    rationale = (
        f"Auto-approved {merchant} ${amount:g} for employee {employee_id}: "
        f"matches prior-approved pattern (under ${cap:g} cap)."
    )
    await asyncio.to_thread(
        _log_action,
        company_id, p.get("id"), transaction_id,
        "auto_approve_expense", merchant, amount, rationale,
    )
    return {
        "autonomous": True,
        "action": "approve_expense",
        "merchant": merchant,
        "amount": amount,
        "rationale": rationale,
        "message": f"Auto-approved {merchant} ${amount:g} — matches prior-approved pattern.",
    }
