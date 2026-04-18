"""
Command router — parses founder iMessage commands and routes them to the correct
action. Returns a structured result dict that main.py turns into a response.

Supported commands (from spec):
  cancel [subscription]              → find sub, trigger headless cancel or email
  negotiate the [vendor] renewal     → start negotiation state machine
  downgrade [tool] to N seats        → draft downgrade email / portal action
  email the team about [topic]       → draft team broadcast, preview, send on confirm
  approve [pending expense / ID]     → mark alert as Y
  reject [pending expense / ID]      → mark alert as N
  change [policy] to [value]         → update policy threshold
  show pending                       → list open alerts
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from dedalus_labs import AsyncDedalus, DedalusRunner

from agents.negotiate import negotiate_agent
from flux_persona import FLUX_PERSONA
from supabase_client import get_supabase
from services.imessage_sender import send_to_founder, FOUNDER_PHONE, send_text

_COMPANY_ID = os.getenv("FLUX_COMPANY_ID", "00000001-0000-4000-8000-000000000001")

# ── Intent classification ─────────────────────────────────────────────────────

_CMD_CLASSIFY_PROMPT = """
Classify this founder message as a command and extract entities.

Message: {message}

Commands:
  cancel        – cancel a subscription (extract: vendor)
  negotiate     – start renewal negotiation (extract: vendor)
  downgrade     – reduce seats or plan (extract: vendor, seats=number or null)
  email_team    – draft team broadcast (extract: topic)
  approve       – approve a pending expense or alert (extract: target=name/id/null)
  reject        – reject a pending expense or alert (extract: target=name/id/null)
  update_policy – change a policy setting (extract: policy_type, value)
  show_pending  – list open alerts
  unknown       – not a command

Return ONLY JSON: {{"command":"...","vendor":null,"seats":null,"topic":null,"target":null,"policy_type":null,"value":null}}
"""


async def _classify_command(message: str, api_key: str) -> dict[str, Any]:
    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    resp = await runner.run(
        input=_CMD_CLASSIFY_PROMPT.format(message=message),
        model="anthropic/claude-haiku-4-5",
        max_tokens=120,
        instructions="Return only valid JSON. No markdown.",
    )
    raw = (resp.final_output or "").strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"command": "unknown"}


# ── Action handlers ───────────────────────────────────────────────────────────

def _fetch_subscription(company_id: str, vendor: str) -> list[dict[str, Any]]:
    resp = (
        get_supabase()
        .table("subscription_renewals")
        .select("*")
        .eq("company_id", company_id)
        .ilike("vendor", f"%{vendor}%")
        .limit(3)
        .execute()
    )
    return list(resp.data or [])


async def _handle_cancel(company_id: str, vendor: str) -> dict[str, Any]:
    subs = await asyncio.to_thread(_fetch_subscription, company_id, vendor)
    if not subs:
        return {
            "reply": f"No active subscription found for {vendor}. Check the dashboard for the full list.",
            "pillar": "saas_sprawl",
        }
    sub = subs[0]
    cost = float(sub.get("current_monthly_cost") or 0)
    renewal = sub.get("renewal_date", "unknown")
    vendor_name = sub.get("vendor", vendor)

    # Create a pending cancel alert for founder confirmation
    get_supabase().table("agent_alerts").insert({
        "company_id": company_id,
        "pillar": "saas_sprawl",
        "alert_type": "cancel_requested",
        "message": (
            f"Cancel {vendor_name} requested. ${cost:g}/mo · renewal {renewal}. "
            f"Negotiation email queued — confirm to send?"
        ),
        "requires_action": True,
        "action_prompt": "Confirm cancellation email to vendor?",
    }).execute()

    return {
        "reply": (
            f"Found {vendor_name} — ${cost:g}/mo, renewal {renewal}. "
            f"Drafting cancellation email. Reply Y to send."
        ),
        "pillar": "saas_sprawl",
        "action": "cancel_pending",
        "vendor": vendor_name,
        "monthly_cost": cost,
    }


async def _handle_negotiate(company_id: str, vendor: str) -> dict[str, Any]:
    subs = await asyncio.to_thread(_fetch_subscription, company_id, vendor)
    current_price = float(subs[0].get("current_monthly_cost") or 500) if subs else 500.0
    vendor_name = subs[0].get("vendor", vendor) if subs else vendor

    result = await negotiate_agent(vendor_name, current_price, 15.0, company_id)
    draft = result.get("email_draft", "")

    # Start negotiation thread (pending state)
    from services.negotiation_sm import start_negotiation
    thread = await start_negotiation(
        company_id=company_id,
        vendor=vendor_name,
        original_price=current_price,
        target_pct=15.0,
        draft_email=draft,
        floor_pct=5.0,
    )
    thread_id = thread.get("id", "")

    # Show draft preview — ask for approval
    preview = draft[:300] + ("..." if len(draft) > 300 else "")
    return {
        "reply": f"Negotiation email drafted for {vendor_name}:\n\n{preview}\n\nReply Y to send.",
        "pillar": "saas_sprawl",
        "action": "negotiate_pending",
        "thread_id": thread_id,
        "vendor": vendor_name,
        "draft": draft,
    }


async def _handle_downgrade(company_id: str, vendor: str, seats: Any) -> dict[str, Any]:
    subs = await asyncio.to_thread(_fetch_subscription, company_id, vendor)
    vendor_name = subs[0].get("vendor", vendor) if subs else vendor
    seats_str = f"to {seats} seats" if seats else "to a lower plan"

    msg = (
        f"Downgrade email to {vendor_name} {seats_str} queued. "
        f"Reply Y to send."
    )
    get_supabase().table("agent_alerts").insert({
        "company_id": company_id,
        "pillar": "saas_sprawl",
        "alert_type": "downgrade_requested",
        "message": msg,
        "requires_action": True,
        "action_prompt": "Confirm downgrade email to vendor?",
    }).execute()
    return {"reply": msg, "pillar": "saas_sprawl", "action": "downgrade_pending", "vendor": vendor_name}


async def _handle_email_team(company_id: str, topic: str, api_key: str) -> dict[str, Any]:
    # Draft using Dedalus
    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    resp = await runner.run(
        input=f"Draft a short, professional all-hands Slack/email message about: {topic}",
        model="anthropic/claude-sonnet-4-6",
        max_tokens=300,
        instructions=FLUX_PERSONA,
    )
    draft = (resp.final_output or "").strip()
    preview = draft[:280] + ("..." if len(draft) > 280 else "")
    return {
        "reply": f"Draft:\n\n{preview}\n\nReply Y to send to all employees.",
        "action": "email_team_pending",
        "draft": draft,
        "topic": topic,
    }


def _resolve_pending_alert(company_id: str, choice: str) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("agent_alerts")
        .select("*")
        .eq("company_id", company_id)
        .eq("resolved", False)
        .eq("requires_action", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    alerts = resp.data or []
    if not alerts:
        return {"reply": "No pending items to approve/reject."}
    alert = alerts[0]
    get_supabase().table("agent_alerts").update({
        "resolved": True,
        "founder_action": choice,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", alert["id"]).execute()
    # Also mark on transaction
    if alert.get("transaction_id"):
        get_supabase().table("transactions").update({"founder_action": choice}).eq("id", alert["transaction_id"]).execute()
    verb = "Approved" if choice == "Y" else "Rejected"
    return {"reply": f"✅ {verb}: {alert.get('message', '')[:80]}"}


def _list_pending(company_id: str) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("agent_alerts")
        .select("alert_type, message, created_at")
        .eq("company_id", company_id)
        .eq("resolved", False)
        .eq("requires_action", True)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    items = resp.data or []
    if not items:
        return {"reply": "No pending items."}
    lines = [f"{i+1}. {it.get('message','')[:70]}" for i, it in enumerate(items)]
    return {"reply": "Pending:\n" + "\n".join(lines)}


def _update_policy(company_id: str, policy_type: str, value: str) -> dict[str, Any]:
    # Map text policy names to db types
    type_map = {
        "auto-cancel": "auto_cancel",
        "auto cancel": "auto_cancel",
        "cancel threshold": "auto_cancel",
        "auto-accept": "auto_accept_discount",
        "discount": "auto_accept_discount",
        "expense": "auto_approve_expense",
        "auto-approve": "auto_approve_expense",
    }
    db_type = type_map.get(policy_type.lower().strip())
    if not db_type:
        # Try direct match
        db_type = policy_type.lower().replace(" ", "_").replace("-", "_")

    # Extract numeric value
    nums = [s for s in value.replace("$", "").split() if s.replace(".", "").isdigit()]
    if not nums:
        return {"reply": f"Couldn't parse a numeric value from '{value}'."}

    num = float(nums[0])
    # Decide which field to update
    field = "threshold_amount"
    if "day" in value.lower():
        field = "threshold_days"
        num = int(num)
    elif "%" in value or "pct" in value.lower() or "percent" in value.lower():
        field = "threshold_discount_pct"

    get_supabase().table("policies").update({field: num, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("company_id", company_id).eq("type", db_type).execute()

    return {
        "reply": f"Updated {db_type.replace('_', ' ')} policy: {field.replace('_', ' ')} → {num}.",
        "action": "policy_updated",
    }


# ── Main dispatcher ───────────────────────────────────────────────────────────

async def route_command(message: str, company_id: str) -> dict[str, Any]:
    """Parse a founder command and return an action result dict."""
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        return {"reply": "DEDALUS_API_KEY not set.", "command": "unknown"}

    params = await _classify_command(message, api_key)
    command = params.get("command", "unknown")

    if command == "cancel":
        return await _handle_cancel(company_id, params.get("vendor") or "")

    if command == "negotiate":
        return await _handle_negotiate(company_id, params.get("vendor") or "")

    if command == "downgrade":
        return await _handle_downgrade(company_id, params.get("vendor") or "", params.get("seats"))

    if command == "email_team":
        return await _handle_email_team(company_id, params.get("topic") or "", api_key)

    if command == "approve":
        return await asyncio.to_thread(_resolve_pending_alert, company_id, "Y")

    if command == "reject":
        return await asyncio.to_thread(_resolve_pending_alert, company_id, "N")

    if command == "show_pending":
        return await asyncio.to_thread(_list_pending, company_id)

    if command == "update_policy":
        return await asyncio.to_thread(
            _update_policy, company_id,
            params.get("policy_type") or "",
            params.get("value") or "",
        )

    return {"reply": None, "command": "unknown"}
