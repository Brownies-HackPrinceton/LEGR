"""
Restraint filter — decides when and how to surface an agent result to the founder.

Three tiers:
  urgent          → send immediately, any hour
  decision_needed → send during business hours (08:00–21:00 founder local time)
  informational   → hold for Monday morning brief and Friday digest

Every decision is logged to restraint_log in Supabase.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from supabase_client import get_supabase

Tier = Literal["urgent", "decision_needed", "informational"]

# Founder timezone offset from UTC (default: US/Pacific = -7 during PDT)
_TZ_OFFSET_H = int(os.getenv("FOUNDER_TZ_OFFSET", "-7"))
_BIZ_START = 8
_BIZ_END = 21


def _local_hour() -> int:
    utc_hour = datetime.now(timezone.utc).hour
    return (utc_hour + _TZ_OFFSET_H) % 24


def _is_business_hours() -> bool:
    return _BIZ_START <= _local_hour() < _BIZ_END


def classify_tier(result: dict[str, Any]) -> tuple[Tier, str]:
    """Return (tier, human-readable reason) for a given agent result dict."""
    agent = str(result.get("agent") or "").lower()
    requires_action = bool(result.get("requires_action", False))
    spike = bool(result.get("spike_detected", False))
    flags = result.get("flags") or []
    amount = float(result.get("amount") or 0)
    days_until_renewal = int(result.get("days_until_renewal") or 999)
    below_floor = bool(result.get("below_policy_floor", False))
    confidence = float(result.get("confidence") or 1.0)

    # ── URGENT ────────────────────────────────────────────────
    if spike and agent == "ai_spend":
        return "urgent", "AI cost spike detected (>2x weekly baseline)"

    if agent == "compliance" and requires_action:
        bad = {"fraud", "strip", "casino", "gambling", "liquor", "cash advance"}
        if any(f.lower() in bad for f in flags):
            return "urgent", "Potential fraud or policy-violation requiring founder decision"

    if below_floor:
        return "urgent", "Negotiation counter below policy floor"

    if agent == "flag_for_founder" and amount > 500:
        return "urgent", f"Unknown merchant charge ${amount:g} — over $500 requires immediate attention"

    # ── DECISION NEEDED ───────────────────────────────────────
    if days_until_renewal <= 7:
        return "decision_needed", f"Renewal decision needed within {days_until_renewal} day(s)"

    if agent == "flag_for_founder" and amount > 200:
        return "decision_needed", f"Unknown merchant ${amount:g} — needs one-time categorization"

    if requires_action and confidence >= 0.7:
        return "decision_needed", "Agent identified action requiring founder approval"

    # ── INFORMATIONAL ─────────────────────────────────────────
    return "informational", "Routine action; will be bundled in digest"


def should_send_now(tier: Tier) -> bool:
    if tier == "urgent":
        return True
    if tier == "decision_needed":
        return _is_business_hours()
    return False  # informational → digest


async def log_restraint(
    company_id: str,
    alert_id: Optional[str],
    tier: Tier,
    reason: str,
    sent: bool,
) -> None:
    def _write() -> None:
        supabase = get_supabase()
        supabase.table("restraint_log").insert({
            "company_id": company_id,
            "alert_id": alert_id,
            "tier": tier,
            "reason": reason,
            "sent": sent,
            "sent_at": datetime.now(timezone.utc).isoformat() if sent else None,
        }).execute()

    try:
        await asyncio.to_thread(_write)
    except Exception:
        pass
