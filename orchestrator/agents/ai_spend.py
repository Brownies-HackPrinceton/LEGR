from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any

from dedalus_labs import AsyncDedalus, DedalusRunner

from flux_persona import FLUX_PERSONA
from supabase_client import get_supabase

_SAVINGS_ACTION_THRESHOLD = 500.0


def _merchant_vendor_fragment(merchant: str) -> str:
    parts = (merchant or "").strip().split()
    return parts[0].lower() if parts else ""


def _fetch_ai_usage_history(company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    fragment = _merchant_vendor_fragment(merchant)
    q = supabase.table("ai_usage").select("*").eq("company_id", company_id)
    if fragment:
        q = q.ilike("vendor", f"%{fragment}%")
    resp = q.order("week_start", desc=True).limit(8).execute()
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _weekly_totals(rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
    by_week: dict[str, float] = defaultdict(float)
    for r in rows:
        ws = r.get("week_start")
        if ws is None:
            continue
        key = str(ws)
        by_week[key] += float(r.get("total_cost") or 0)
    return sorted(by_week.items(), key=lambda x: x[0], reverse=True)


def _spike_wow_gt_100pct(rows: list[dict[str, Any]]) -> bool:
    weeks = _weekly_totals(rows)
    if len(weeks) < 2:
        return False
    latest_cost = weeks[0][1]
    prev_cost = weeks[1][1]
    if prev_cost <= 0:
        return latest_cost > 0
    return (latest_cost - prev_cost) / prev_cost > 1.0


def _max_potential_savings(rows: list[dict[str, Any]]) -> float:
    best = 0.0
    for r in rows:
        raw = r.get("potential_savings")
        if raw is None:
            continue
        try:
            best = max(best, float(raw))
        except (TypeError, ValueError):
            continue
    return best


def _fallback_founder_message(merchant: str, amount: float, rows: list[dict[str, Any]], spike: bool) -> str:
    if not rows:
        return f"No ai_usage history matched for {merchant!r} at ${amount:g}. Link usage export or wait for weekly sync."
    week_starts = [r.get("week_start") for r in rows if r.get("week_start")]
    if not week_starts:
        return f"ai_usage rows for {merchant} lack week_start; cannot summarize."
    latest_week = max(week_starts, key=lambda x: str(x))
    week_rows = [r for r in rows if r.get("week_start") == latest_week]
    if not week_rows:
        return f"No rows for latest week {latest_week!r}."
    driver = max(week_rows, key=lambda r: float(r.get("total_cost") or 0))
    calls = int(driver.get("call_count") or 0)
    model = driver.get("model")
    use_case = driver.get("use_case")
    rec = driver.get("recommended_model")
    sav = driver.get("potential_savings")
    spike_txt = "Spike vs prior week (>100% WoW)." if spike else "Spend trend within prior-week range."
    return (
        f"{merchant} bill context: ${amount:g} (invoice vs internal usage rows). {spike_txt} "
        f"Latest week row: {calls:,} calls on {model} for {use_case!r}. "
        f"Recommended routing: {rec!r} saves ~${float(sav or 0):,.0f}/mo. Deploy routing middleware?"
    )


async def ai_spend_agent(merchant: str, amount: float, company_id: str) -> dict[str, Any]:
    """Analyzes AI vendor charge for spike/routing issues. Queries ai_usage history and reasons via Dedalus."""
    if not _merchant_vendor_fragment(merchant):
        return {
            "pillar": "ai_spend",
            "spike_detected": False,
            "message": "Missing merchant name; cannot match ai_usage.vendor.",
            "requires_action": False,
            "action_prompt": "Deploy routing middleware?",
        }

    rows = await asyncio.to_thread(_fetch_ai_usage_history, company_id, merchant)
    spike_detected = _spike_wow_gt_100pct(rows)
    max_savings = _max_potential_savings(rows)
    requires_action = spike_detected or max_savings >= _SAVINGS_ACTION_THRESHOLD

    api_key = os.getenv("DEDALUS_API_KEY")
    history_payload = rows
    narrative: str

    if api_key:
        client = AsyncDedalus(api_key=api_key)
        runner = DedalusRunner(client)
        prompt = f"""Analyze this AI spend for {merchant} at ${amount:g}.
Historical weekly rows (newest first in this JSON): {history_payload}

Identify:
1. Is there a spike? (>100% WoW growth in total_cost for this vendor vs the prior week in the data)
2. What use_case is driving the latest week's cost?
3. Is there a recommended_model with savings > $500/mo (see potential_savings)?
4. Phrase a short founder alert: "X bill hit $Y. +Z% from last week. Traced: [use_case]. [recommended_model] saves $N/mo. Deploy?"

Use the numbers in the data (call_count, total_cost, potential_savings). Be specific (e.g. Opus call volume, Haiku savings).
"""
        try:
            analysis = await runner.run(
                input=prompt,
                model="anthropic/claude-sonnet-4-6",
                max_tokens=600,
                instructions=FLUX_PERSONA,
            )
            narrative = (analysis.final_output or "").strip()
        except Exception as exc:  # noqa: BLE001 — demo path: still return structured result
            narrative = _fallback_founder_message(merchant, amount, rows, spike_detected) + f" (Dedalus error: {exc})"
    else:
        narrative = _fallback_founder_message(merchant, amount, rows, spike_detected)

    if not narrative:
        narrative = _fallback_founder_message(merchant, amount, rows, spike_detected)

    return {
        "agent": "ai_spend",
        "pillar": "ai_spend",
        "spike_detected": spike_detected,
        "message": narrative,
        "requires_action": requires_action,
        "action_prompt": "Deploy routing middleware?",
    }
