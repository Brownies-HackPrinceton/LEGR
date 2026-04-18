from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

from dedalus_labs import AsyncDedalus, DedalusRunner

from flux_persona import FLUX_PERSONA
from supabase_client import get_supabase


@dataclass(frozen=True)
class _Opportunity:
    kind: str
    savings_monthly: float
    summary: str


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fetch_seats(*, company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("seat_usage")
        .select("*")
        .eq("company_id", company_id)
        .eq("tool", merchant)
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _fetch_renewal(*, company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("subscription_renewals")
        .select("*")
        .eq("company_id", company_id)
        .eq("vendor", merchant)
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _fetch_overlap(*, company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("tool_overlaps")
        .select("*")
        .eq("company_id", company_id)
        .contains("tools", [merchant])
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _fetch_feature_waste(*, company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("feature_waste")
        .select("*")
        .eq("company_id", company_id)
        .eq("vendor", merchant)
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _fetch_tier(*, company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("plan_optimization")
        .select("*")
        .eq("company_id", company_id)
        .eq("vendor", merchant)
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _fetch_shadow(*, company_id: str, merchant: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("shadow_it")
        .select("*")
        .eq("company_id", company_id)
        .eq("vendor", merchant)
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _seat_opportunity(*, merchant: str, seats: list[dict[str, Any]], renewal: list[dict[str, Any]]) -> Optional[_Opportunity]:
    if not seats:
        return None
    dormant = sum(1 for s in seats if bool(s.get("is_dormant")))
    total = len(seats)
    if dormant <= 0 or total <= 0:
        return None

    monthly_cost = 0.0
    if renewal:
        monthly_cost = _safe_float(renewal[0].get("monthly_cost"))
    est_savings = (dormant / total) * monthly_cost if monthly_cost > 0 else 0.0
    summary = f"{merchant}: {dormant}/{total} seats look dormant. Right-size seats to cut waste."
    return _Opportunity("ghost_seats", est_savings, summary)


def _tier_opportunity(*, tier: list[dict[str, Any]]) -> Optional[_Opportunity]:
    if not tier:
        return None
    best = max(tier, key=lambda r: _safe_float(r.get("monthly_savings")))
    savings = _safe_float(best.get("monthly_savings"))
    if savings <= 0:
        return None
    vendor = str(best.get("vendor") or "Vendor")
    cur = best.get("current_plan")
    rec = best.get("recommended_plan")
    reason = best.get("reason")
    return _Opportunity("plan_optimization", savings, f"{vendor}: downgrade {cur!r} → {rec!r} saves ~${savings:,.0f}/mo ({reason}).")


def _overlap_opportunity(*, overlap: list[dict[str, Any]]) -> Optional[_Opportunity]:
    if not overlap:
        return None
    best = max(overlap, key=lambda r: _safe_float(r.get("estimated_savings")))
    savings = _safe_float(best.get("estimated_savings"))
    if savings <= 0:
        return None
    tools = best.get("tools")
    rec = best.get("recommended_consolidation")
    return _Opportunity("tool_overlap", savings, f"Tool overlap {tools}: {rec} (save ~${savings:,.0f}/mo).")


def _feature_waste_opportunity(*, waste: list[dict[str, Any]]) -> Optional[_Opportunity]:
    if not waste:
        return None
    best = max(waste, key=lambda r: _safe_float(r.get("monthly_cost")))
    savings = _safe_float(best.get("monthly_cost"))
    if savings <= 0:
        return None
    vendor = str(best.get("vendor") or "Vendor")
    feature = best.get("feature")
    rec = best.get("recommendation")
    return _Opportunity("feature_waste", savings, f"{vendor}: {feature!r} costs ~${savings:,.0f}/mo. Recommendation: {rec}.")


def _shadow_it_opportunity(*, shadow: list[dict[str, Any]]) -> Optional[_Opportunity]:
    if not shadow:
        return None
    # Shadow IT is usually risk-driven (not pure savings), but we can surface the biggest monthly cost.
    best = max(shadow, key=lambda r: _safe_float(r.get("monthly_cost")))
    cost = _safe_float(best.get("monthly_cost"))
    vendor = str(best.get("vendor") or "Vendor")
    risk = best.get("risk_level")
    return _Opportunity("shadow_it", cost, f"{vendor}: shadow IT charge ~${cost:,.0f}/mo (risk={risk}). Review/approve or consolidate.")


def _pick_biggest(opps: list[_Opportunity]) -> Optional[_Opportunity]:
    if not opps:
        return None
    return max(opps, key=lambda o: o.savings_monthly)


def _fallback_message(
    *,
    merchant: str,
    amount: float,
    seats: list[dict[str, Any]],
    renewal: list[dict[str, Any]],
    overlap: list[dict[str, Any]],
    waste: list[dict[str, Any]],
    tier: list[dict[str, Any]],
    shadow: list[dict[str, Any]],
) -> str:
    opps: list[_Opportunity] = []
    seat_opp = _seat_opportunity(merchant=merchant, seats=seats, renewal=renewal)
    if seat_opp:
        opps.append(seat_opp)
    for maybe in (
        _tier_opportunity(tier=tier),
        _overlap_opportunity(overlap=overlap),
        _feature_waste_opportunity(waste=waste),
        _shadow_it_opportunity(shadow=shadow),
    ):
        if maybe:
            opps.append(maybe)

    top = _pick_biggest(opps)

    renewal_line = ""
    if renewal:
        r0 = renewal[0]
        renewal_line = (
            f" Renewal: {r0.get('billing_cycle')} {r0.get('plan_tier')} @ "
            f"${_safe_float(r0.get('monthly_cost')):,.0f}/mo renews {r0.get('renewal_date')}."
        )

    if top:
        return f"{merchant} charge ${amount:g}.{renewal_line} Biggest lever: {top.summary}"

    # No strong signals found for this merchant.
    return f"{merchant} charge ${amount:g}.{renewal_line} No seat/renewal/overlap/tier/waste signals found yet."


async def saas_agent(merchant: str, amount: float, company_id: str) -> dict[str, Any]:
    """Analyzes SaaS charge — seat usage, renewals, overlaps, feature waste, shadow IT."""
    seats_t = asyncio.to_thread(_fetch_seats, company_id=company_id, merchant=merchant)
    renewal_t = asyncio.to_thread(_fetch_renewal, company_id=company_id, merchant=merchant)
    overlap_t = asyncio.to_thread(_fetch_overlap, company_id=company_id, merchant=merchant)
    waste_t = asyncio.to_thread(_fetch_feature_waste, company_id=company_id, merchant=merchant)
    tier_t = asyncio.to_thread(_fetch_tier, company_id=company_id, merchant=merchant)
    shadow_t = asyncio.to_thread(_fetch_shadow, company_id=company_id, merchant=merchant)

    seats, renewal, overlap, waste, tier, shadow = await asyncio.gather(
        seats_t, renewal_t, overlap_t, waste_t, tier_t, shadow_t
    )

    api_key = os.getenv("DEDALUS_API_KEY")
    message: str

    if api_key:
        client = AsyncDedalus(api_key=api_key)
        runner = DedalusRunner(client)
        prompt = f"""SaaS charge: {merchant} for ${amount:g}. Here's everything I found (all from Supabase):

Seats: {seats}
Renewal timeline: {renewal}
Tool overlaps: {overlap}
Feature waste: {waste}
Tier optimization: {tier}
Shadow IT: {shadow}

Write a short founder alert focusing on the BIGGEST savings opportunity.
If multiple signals exist, mention them briefly but lead with the highest-impact one.
Be concrete: include renewal dates, seat counts, and monthly savings numbers when present.
"""
        try:
            analysis = await runner.run(
                input=prompt,
                model="anthropic/claude-sonnet-4-6",
                max_tokens=600,
                instructions=FLUX_PERSONA,
            )
            message = (analysis.final_output or "").strip()
        except Exception as exc:  # noqa: BLE001 — demo path: still return structured result
            message = _fallback_message(
                merchant=merchant,
                amount=amount,
                seats=seats,
                renewal=renewal,
                overlap=overlap,
                waste=waste,
                tier=tier,
                shadow=shadow,
            ) + f" (Dedalus error: {exc})"
    else:
        message = _fallback_message(
            merchant=merchant,
            amount=amount,
            seats=seats,
            renewal=renewal,
            overlap=overlap,
            waste=waste,
            tier=tier,
            shadow=shadow,
        )

    if not message:
        message = _fallback_message(
            merchant=merchant,
            amount=amount,
            seats=seats,
            renewal=renewal,
            overlap=overlap,
            waste=waste,
            tier=tier,
            shadow=shadow,
        )

    return {
        "agent": "saas",
        "pillar": "saas_sprawl",
        "message": message,
        "requires_action": True,
        "action_prompt": "Take action on this SaaS optimization?",
    }

