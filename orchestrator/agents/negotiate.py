from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from dedalus_labs import AsyncDedalus, DedalusRunner

from flux_persona import FLUX_PERSONA
from supabase_client import get_supabase


def _fetch_won_history(company_id: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    resp = (
        supabase.table("negotiation_history")
        .select("*")
        .eq("company_id", company_id)
        .eq("outcome", "won")
        .order("initiated_date", desc=True)
        .limit(5)
        .execute()
    )
    rows = resp.data or []
    return list(rows) if isinstance(rows, list) else []


def _log_initiated(
    *,
    company_id: str,
    vendor: str,
    current_price: float,
    target_discount: float,
    thread_summary: str,
) -> dict[str, Any] | None:
    supabase = get_supabase()
    payload = {
        "company_id": company_id,
        "vendor": vendor,
        "initiated_date": datetime.now(timezone.utc).isoformat(),
        "original_price": current_price,
        "target_discount": target_discount,
        "outcome": "ongoing",
        "thread_summary": (thread_summary or "")[:500],
    }
    resp = supabase.table("negotiation_history").insert(payload).execute()
    rows = resp.data or []
    if isinstance(rows, list) and rows:
        return rows[0] if isinstance(rows[0], dict) else None
    return None


def _fallback_email(vendor: str, current_price: float, target_discount: float) -> str:
    new_price = current_price * (1 - (target_discount / 100.0))
    return (
        f"Subject: {vendor} renewal — pricing adjustment\n\n"
        f"Hi {vendor} team,\n\n"
        f"We’re reviewing renewals across our stack and need to bring {vendor} in line with our 2026 budget. "
        f"We’re currently at ${current_price:,.0f}/mo; we can renew on an annual term if you can offer a {target_discount:g}% discount "
        f"(~${new_price:,.0f}/mo).\n\n"
        f"If that’s workable, please send the updated quote. If not, we’ll likely need to right-size or consider alternatives.\n\n"
        f"Thanks,\n"
        f"[Founder Name]\n"
    )


async def negotiate_agent(vendor: str, current_price: float, target_discount: float, company_id: str) -> dict[str, Any]:
    """Drafts a renewal negotiation email using past negotiation history as context."""
    history: list[dict[str, Any]]
    try:
        history = await asyncio.to_thread(_fetch_won_history, company_id)
    except Exception:
        # Table may not exist yet if migration wasn't applied; still produce a draft.
        history = []

    api_key = os.getenv("DEDALUS_API_KEY")
    draft_text: str

    if api_key:
        client = AsyncDedalus(api_key=api_key)
        runner = DedalusRunner(client)
        prompt = f"""Draft a renewal negotiation email to {vendor}.
Current price: ${current_price:,.0f}/mo
Target: {target_discount:g}% discount

Past wins at this company for tone reference:
{history}

Write a direct, professional email from the founder. 2-3 short paragraphs.
Cite competitive pressure, cost sensitivity, and willingness to commit to annual if discount is granted.
Include a clear ask.
"""
        try:
            draft = await runner.run(
                input=prompt,
                model="anthropic/claude-sonnet-4-6",
                max_tokens=500,
                instructions=FLUX_PERSONA,
            )
            draft_text = (draft.final_output or "").strip()
        except Exception as exc:  # noqa: BLE001 — demo path: still return draft
            draft_text = _fallback_email(vendor, current_price, target_discount) + f"\n(Dedalus error: {exc})"
    else:
        draft_text = _fallback_email(vendor, current_price, target_discount)

    if not draft_text:
        draft_text = _fallback_email(vendor, current_price, target_discount)

    # Log the negotiation as initiated (best-effort).
    try:
        await asyncio.to_thread(
            _log_initiated,
            company_id=company_id,
            vendor=vendor,
            current_price=float(current_price),
            target_discount=float(target_discount),
            thread_summary=draft_text,
        )
    except Exception:
        pass

    return {"agent": "negotiate", "vendor": vendor, "email_draft": draft_text}

