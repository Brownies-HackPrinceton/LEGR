from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Literal, NotRequired, Optional, TypedDict

from dedalus_labs import AsyncDedalus, DedalusRunner

from agents.ai_spend import ai_spend_agent as ai_spend_analyze_charge
from agents.compliance import compliance_agent as compliance_evaluate_swipe
from agents.negotiate import negotiate_agent as negotiate_draft_email
from agents.saas import saas_agent as saas_analyze_charge
from flux_persona import FLUX_PERSONA
from services.imessage_sender import FOUNDER_PHONE, send_to_founder
from services.policy_engine import evaluate_auto_cancel, is_production_infra, evaluate_auto_approve_expense
from services.restraint_filter import classify_tier, log_restraint, should_send_now
from supabase_client import get_supabase


class TransactionIn(TypedDict):
    id: str
    company_id: str
    merchant: str
    amount: float
    submitted_by: str
    memo: Optional[str]
    employee_id: NotRequired[Optional[str]]


class OrchestratorOutput(TypedDict, total=False):
    pillar: Literal["ai_spend", "saas_sprawl", "compliance", "unknown"]
    agent: str
    summary: str
    reasoning: str
    payload: Dict[str, Any]


# ── Agent tool wrappers (Dedalus calls these) ─────────────────────────────────

async def ai_spend_agent(txn: TransactionIn) -> Dict[str, Any]:
    return await ai_spend_analyze_charge(txn["merchant"], float(txn["amount"]), txn["company_id"])


async def saas_agent(txn: TransactionIn) -> Dict[str, Any]:
    # Check auto-cancel policy before routing to human-facing alert
    auto = await evaluate_auto_cancel(
        txn["company_id"],
        txn["merchant"],
        float(txn["amount"]),
        txn.get("id"),
    )
    if auto:
        auto["pillar"] = "saas_sprawl"
        return auto

    return await saas_analyze_charge(txn["merchant"], float(txn["amount"]), txn["company_id"])


async def compliance_agent(txn: TransactionIn) -> Dict[str, Any]:
    eid = txn.get("employee_id")
    if not eid:
        return {
            "agent": "compliance",
            "error": "missing_employee_id",
            "detail": "compliance_agent requires employee_id for employee card swipes",
        }

    # Check auto-approve expense policy before sending human-facing alert
    auto = await evaluate_auto_approve_expense(
        company_id=txn["company_id"],
        employee_id=eid,
        merchant=txn["merchant"],
        amount=float(txn["amount"]),
        transaction_id=txn.get("id"),
    )
    if auto:
        auto["pillar"] = "compliance"
        return auto

    return await compliance_evaluate_swipe(
        txn["merchant"], float(txn["amount"]), eid, txn.get("memo") or ""
    )


async def flag_for_founder(txn: TransactionIn) -> Dict[str, Any]:
    return {
        "agent": "flag_for_founder",
        "pillar": "unknown",
        "amount": float(txn["amount"]),
        "message": f"New charge at {txn['merchant']} (${float(txn['amount']):g}). Category?",
        "requires_action": True,
        "action_prompt": "Reply: ai_spend / saas / compliance / ignore",
    }


async def negotiate_agent(vendor: str, current_price: float, target_discount: float, company_id: str) -> Dict[str, Any]:
    return await negotiate_draft_email(vendor, float(current_price), float(target_discount), company_id)


# ── Alert writer (restraint-filtered) ────────────────────────────────────────

async def write_alert(*, txn: TransactionIn, result: Dict[str, Any]) -> None:
    # If this was an autonomous policy action, send directly (informational tier
    # but founder should know).  Otherwise run through restraint filter.
    autonomous = bool(result.get("autonomous", False))

    def _insert() -> dict[str, Any] | None:
        payload = {
            "company_id": txn["company_id"],
            "transaction_id": txn["id"],
            "pillar": result.get("pillar") or txn.get("pillar"),
            "alert_type": result.get("agent") or result.get("action") or "agent_result",
            "message": result.get("message") or str(result),
            "requires_action": bool(result.get("requires_action", False)),
            "action_prompt": result.get("action_prompt"),
        }
        resp = get_supabase().table("agent_alerts").insert(payload).execute()
        rows = resp.data or []
        return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None

    row = await asyncio.to_thread(_insert)
    alert_id = row.get("id") if row else None

    if not FOUNDER_PHONE:
        return

    # ── Autonomous actions are always informational (bundled in digest) ───────
    if autonomous:
        await log_restraint(txn["company_id"], alert_id, "informational", "autonomous policy action", False)
        # Still send immediately (founders should know within minutes)
        await send_to_founder(
            result.get("message", ""),
            pillar=result.get("pillar"),
            alert_id=alert_id,
        )
        return

    # ── Restraint filter ─────────────────────────────────────────────────────
    tier, reason = classify_tier({**result, "amount": float(txn.get("amount") or 0)})
    send_now = should_send_now(tier)

    await log_restraint(txn["company_id"], alert_id, tier, reason, send_now)

    if not send_now:
        return  # held for digest

    requires_action = bool(result.get("requires_action", False))
    action_prompt = result.get("action_prompt")
    message = str(result.get("message") or "")

    await send_to_founder(
        message,
        poll=requires_action and bool(action_prompt),
        action_prompt=action_prompt,
        pillar=result.get("pillar"),
        alert_id=alert_id,
    )


# ── Orchestrator entry point ──────────────────────────────────────────────────

async def route_transaction(txn: TransactionIn) -> Any:
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEDALUS_API_KEY")
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")

    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)

    response = await runner.run(
        input=f"""New transaction:
Merchant: {txn['merchant']}
Amount:   ${txn['amount']}
By:       {txn['submitted_by']}
Memo:     {txn.get('memo', 'none')}

Classify into ONE pillar and call the right specialist:
  - AI vendors (Anthropic, OpenAI, Replicate, Groq, Mistral) → ai_spend_agent
  - SaaS tools (Cursor, Notion, Figma, Linear, Slack, Vercel, GitHub) → saas_agent
  - Employee expenses (restaurants, travel, retail, hotels) → compliance_agent
  - Unknown → flag_for_founder

Then call write_alert with the transaction and the specialist's result.
""",
        model="anthropic/claude-haiku-4-5",
        tools=[ai_spend_agent, saas_agent, compliance_agent, flag_for_founder, write_alert, negotiate_agent],
        max_tokens=600,
        instructions=FLUX_PERSONA,
    )
    return response.final_output
