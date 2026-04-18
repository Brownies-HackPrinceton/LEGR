"""
Digest service — compiles and sends the Monday morning brief and Friday digest.

Informational-tier alerts that were held by the restraint filter are bundled
here so founders get one clean summary rather than a stream of noise.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase_client import get_supabase
from services.imessage_sender import send_to_founder


def _fetch_unbundled_info(company_id: str) -> list[dict[str, Any]]:
    resp = (
        get_supabase()
        .table("restraint_log")
        .select("*, agent_alerts(message, pillar, created_at)")
        .eq("company_id", company_id)
        .eq("tier", "informational")
        .eq("sent", False)
        .is_("bundled_in_digest_at", "null")
        .order("created_at", desc=False)
        .limit(20)
        .execute()
    )
    return list(resp.data or [])


def _fetch_week_summary(company_id: str) -> dict[str, Any]:
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    supabase = get_supabase()

    txn_resp = (
        supabase.table("transactions")
        .select("amount, pillar, savings_identified")
        .eq("company_id", company_id)
        .gte("created_at", week_ago)
        .execute()
    )
    txns = txn_resp.data or []

    policy_resp = (
        supabase.table("policy_actions")
        .select("action_type, entity_name, amount, rationale")
        .eq("company_id", company_id)
        .gte("executed_at", week_ago)
        .execute()
    )
    actions = policy_resp.data or []

    total_spend = sum(float(t.get("amount") or 0) for t in txns)
    total_savings = sum(float(t.get("savings_identified") or 0) for t in txns)
    total_savings += sum(float(a.get("amount") or 0) for a in actions if "cancel" in str(a.get("action_type")))

    return {
        "total_spend": total_spend,
        "total_savings": total_savings,
        "transaction_count": len(txns),
        "autonomous_actions": len(actions),
        "actions": actions[:5],
    }


def _mark_bundled(log_ids: list[str]) -> None:
    if not log_ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    get_supabase().table("restraint_log").update({"bundled_in_digest_at": now}).in_("id", log_ids).execute()


async def send_morning_brief(company_id: str) -> bool:
    """Monday morning brief — spend summary + pending items."""
    summary = await asyncio.to_thread(_fetch_week_summary, company_id)
    unbundled = await asyncio.to_thread(_fetch_unbundled_info, company_id)

    lines = [
        f"Good morning. Last 7 days:",
        f"${summary['total_spend']:,.0f} in charges across {summary['transaction_count']} transactions.",
        f"${summary['total_savings']:,.0f} in savings identified.",
    ]

    if summary["autonomous_actions"]:
        lines.append(f"\n{summary['autonomous_actions']} autonomous action(s) taken:")
        for a in summary["actions"]:
            lines.append(f"  • {a.get('action_type', '').replace('_', ' ').title()}: {a.get('entity_name')} — {a.get('rationale', '')[:60]}")

    if unbundled:
        lines.append(f"\n{len(unbundled)} routine item(s) held from last week:")
        for u in unbundled[:5]:
            alert = u.get("agent_alerts") or {}
            msg = alert.get("message") or u.get("reason") or ""
            lines.append(f"  • {msg[:80]}")

    text = "\n".join(lines)
    ok = await send_to_founder(text, pillar="ai_spend")

    if ok and unbundled:
        ids = [u["id"] for u in unbundled if u.get("id")]
        await asyncio.to_thread(_mark_bundled, ids)

    return ok


async def send_friday_digest(company_id: str) -> bool:
    """Friday digest — same structure as morning brief but labelled as weekly wrap."""
    summary = await asyncio.to_thread(_fetch_week_summary, company_id)
    unbundled = await asyncio.to_thread(_fetch_unbundled_info, company_id)

    lines = [
        f"Weekly wrap:",
        f"${summary['total_spend']:,.0f} spent · ${summary['total_savings']:,.0f} saved · "
        f"{summary['autonomous_actions']} auto-actions.",
    ]

    if unbundled:
        lines.append(f"\nHeld this week ({len(unbundled)} items):")
        for u in unbundled[:8]:
            alert = u.get("agent_alerts") or {}
            msg = alert.get("message") or ""
            lines.append(f"  • {msg[:80]}")

    text = "\n".join(lines)
    ok = await send_to_founder(text, pillar="ai_spend")

    if ok and unbundled:
        ids = [u["id"] for u in unbundled if u.get("id")]
        await asyncio.to_thread(_mark_bundled, ids)

    return ok
