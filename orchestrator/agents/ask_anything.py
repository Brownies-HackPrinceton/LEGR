"""
Ask-Anything agent — answers natural-language questions about spend, subscriptions,
usage, and expenses in under 3 seconds.

Approach:
1. Classify the question into one of 8 known intents via Dedalus (Haiku model).
2. Execute the corresponding direct Supabase query (no raw SQL needed for known intents).
3. For unknown intents, fall through to the flux_query RPC with generated SQL.
4. Format a short conversational response and cache it for 5 minutes.

Known intents and spec examples they cover:
  ai_spend_total    → "what did we spend on AI last month"
  inactive_seats    → "who's not using Linear"
  cancel_savings    → "how much will we save if I cancel Midjourney"
  recent_charges    → "show me every charge over $500 this week"
  employee_spend    → "what's Sarah's expense total this quarter"
  upcoming_renewals → "which of our subs renew in the next 30 days"
  policy_actions    → "what did Flux do autonomously this week"
  savings_total     → "how much have we saved total"
  general           → fallback to flux_query RPC
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from dedalus_labs import AsyncDedalus, DedalusRunner

from flux_persona import FLUX_PERSONA
from supabase_client import get_supabase

# Avoid circular imports at module level
from services.memory import get_chat_history, get_relevant_memories, save_chat_message

_COMPANY_ID_DEFAULT = os.getenv("FLUX_COMPANY_ID", "00000001-0000-4000-8000-000000000001")

# ── Cache ─────────────────────────────────────────────────────────────────────

def _cache_key(company_id: str, q: str) -> str:
    return hashlib.sha256(f"{company_id}:{q.lower().strip()}".encode()).hexdigest()[:16]


def _cache_read(company_id: str, q: str) -> Optional[str]:
    key = _cache_key(company_id, q)
    resp = (
        get_supabase()
        .table("query_cache")
        .select("answer")
        .eq("company_id", company_id)
        .eq("question_hash", key)
        .gte("expires_at", datetime.now(timezone.utc).isoformat())
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0].get("answer") if rows else None


def _cache_write(company_id: str, q: str, answer: str) -> None:
    key = _cache_key(company_id, q)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    try:
        get_supabase().table("query_cache").upsert({
            "company_id": company_id,
            "question_hash": key,
            "question": q,
            "answer": answer,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": exp,
        }).execute()
    except Exception:
        pass


# ── Time helpers ──────────────────────────────────────────────────────────────

def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _quarter_start() -> str:
    now = datetime.now(timezone.utc)
    q_month = ((now.month - 1) // 3) * 3 + 1
    return datetime(now.year, q_month, 1, tzinfo=timezone.utc).isoformat()


def _month_start() -> str:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()


def _days_from_now(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


# ── Intent-specific query executors ───────────────────────────────────────────

def _run_ai_spend_total(company_id: str, since: str) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("transactions")
        .select("merchant, amount, created_at")
        .eq("company_id", company_id)
        .eq("pillar", "ai_spend")
        .gte("created_at", since)
        .order("amount", desc=True)
        .execute()
    )
    rows = resp.data or []
    total = sum(float(r.get("amount") or 0) for r in rows)
    by_vendor: dict[str, float] = {}
    for r in rows:
        m = r.get("merchant", "Unknown")
        by_vendor[m] = by_vendor.get(m, 0) + float(r.get("amount") or 0)
    return {"total": total, "by_vendor": by_vendor, "row_count": len(rows)}


def _run_inactive_seats(company_id: str, tool: Optional[str]) -> dict[str, Any]:
    q = (
        get_supabase()
        .table("seat_usage")
        .select("*, employees(name, email, role)")
        .eq("company_id", company_id)
        .eq("is_dormant", True)
    )
    if tool:
        q = q.ilike("tool", f"%{tool}%")
    resp = q.order("last_active_date", desc=False).execute()
    rows = resp.data or []
    return {"rows": rows, "count": len(rows)}


def _run_cancel_savings(company_id: str, vendor: str) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("subscription_renewals")
        .select("*")
        .eq("company_id", company_id)
        .ilike("vendor", f"%{vendor}%")
        .limit(3)
        .execute()
    )
    rows = resp.data or []
    return {"rows": rows, "vendor": vendor}


def _run_recent_charges(company_id: str, min_amount: float, since: str) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("transactions")
        .select("merchant, amount, submitted_by, created_at, pillar")
        .eq("company_id", company_id)
        .gte("amount", min_amount)
        .gte("created_at", since)
        .order("amount", desc=True)
        .limit(20)
        .execute()
    )
    rows = resp.data or []
    return {"rows": rows, "count": len(rows)}


def _run_employee_spend(company_id: str, employee_name: str, since: str) -> dict[str, Any]:
    # Find employee by name first
    emp_resp = (
        get_supabase()
        .table("employees")
        .select("id, name")
        .eq("company_id", company_id)
        .ilike("name", f"%{employee_name}%")
        .limit(3)
        .execute()
    )
    employees = emp_resp.data or []
    if not employees:
        return {"total": 0, "employee": employee_name, "not_found": True}

    emp_ids = [e["id"] for e in employees]
    txn_resp = (
        get_supabase()
        .table("transactions")
        .select("merchant, amount, created_at, memo")
        .eq("company_id", company_id)
        .in_("employee_id", emp_ids)
        .gte("created_at", since)
        .order("amount", desc=True)
        .execute()
    )
    rows = txn_resp.data or []
    total = sum(float(r.get("amount") or 0) for r in rows)
    return {"total": total, "rows": rows, "employee": employees[0].get("name")}


def _run_upcoming_renewals(company_id: str, days: int) -> dict[str, Any]:
    cutoff = _days_from_now(days)
    today = datetime.now(timezone.utc).date().isoformat()
    resp = (
        get_supabase()
        .table("subscription_renewals")
        .select("*")
        .eq("company_id", company_id)
        .gte("renewal_date", today)
        .lte("renewal_date", cutoff)
        .order("renewal_date")
        .execute()
    )
    rows = resp.data or []
    total = sum(float(r.get("current_monthly_cost") or 0) for r in rows)
    return {"rows": rows, "count": len(rows), "total_monthly": total}


def _run_policy_actions(company_id: str, since: str) -> dict[str, Any]:
    resp = (
        get_supabase()
        .table("policy_actions")
        .select("*")
        .eq("company_id", company_id)
        .gte("executed_at", since)
        .order("executed_at", desc=True)
        .limit(10)
        .execute()
    )
    rows = resp.data or []
    total_saved = sum(float(r.get("amount") or 0) for r in rows if "cancel" in str(r.get("action_type")))
    return {"rows": rows, "count": len(rows), "total_saved": total_saved}


def _run_savings_total(company_id: str) -> dict[str, Any]:
    txn_resp = (
        get_supabase()
        .table("transactions")
        .select("savings_identified")
        .eq("company_id", company_id)
        .execute()
    )
    txn_savings = sum(float(r.get("savings_identified") or 0) for r in (txn_resp.data or []))

    policy_resp = (
        get_supabase()
        .table("policy_actions")
        .select("amount, action_type")
        .eq("company_id", company_id)
        .execute()
    )
    policy_savings = sum(
        float(r.get("amount") or 0)
        for r in (policy_resp.data or [])
        if "cancel" in str(r.get("action_type"))
    )
    return {"from_agents": txn_savings, "from_policy": policy_savings, "total": txn_savings + policy_savings}


def _run_overview_brief(company_id: str) -> dict[str, Any]:
    # 7 days ago, 14 days ago, +7 days
    now = datetime.now(timezone.utc)
    lw_start = (now - timedelta(days=7)).isoformat()
    pw_start = (now - timedelta(days=14)).isoformat()
    nw_end = (now + timedelta(days=7)).date().isoformat()
    today = now.date().isoformat()

    db = get_supabase()

    # Spend
    lw_txns = db.table("transactions").select("amount, merchant").eq("company_id", company_id).gte("created_at", lw_start).execute().data or []
    pw_txns = db.table("transactions").select("amount, merchant").eq("company_id", company_id).gte("created_at", pw_start).lt("created_at", lw_start).execute().data or []
    
    lw_spend = sum(float(t.get("amount") or 0) for t in lw_txns)
    pw_spend = sum(float(t.get("amount") or 0) for t in pw_txns)
    
    lw_merchants = set(t.get("merchant") for t in lw_txns)
    pw_merchants = set(t.get("merchant") for t in pw_txns)
    new_merchants = list(lw_merchants - pw_merchants)

    # Renewals
    ren = db.table("subscription_renewals").select("*").eq("company_id", company_id).gte("renewal_date", today).lte("renewal_date", nw_end).execute().data or []
    ren_total = sum(float(r.get("current_monthly_cost") or 0) for r in ren)

    # Policy actions
    pol = db.table("policy_actions").select("*").eq("company_id", company_id).gte("executed_at", lw_start).execute().data or []
    total_saved = sum(float(p.get("amount") or 0) for p in pol if "cancel" in str(p.get("action_type")))

    return {
        "spend_last_7_days": lw_spend,
        "spend_prior_7_days": pw_spend,
        "spend_pct_change": round(((lw_spend - pw_spend) / pw_spend * 100) if pw_spend else 0, 1),
        "new_saas_found": new_merchants,
        "upcoming_renewals_count": len(ren),
        "upcoming_renewals_cost": ren_total,
        "auto_handled_actions_count": len(pol),
        "total_saved_last_7_days": total_saved
    }

# ── Intent classifier + response formatter ────────────────────────────────────

_INTENT_PROMPT = """
Classify this question into one intent and extract key parameters.

Question: {question}

Intents:
  ai_spend_total    – total AI spend (extract: period="last_month"|"last_week"|"this_month")
  inactive_seats    – unused tool seats (extract: tool=vendor name or null)
  cancel_savings    – savings from cancelling a tool (extract: vendor=name)
  recent_charges    – list of transactions by amount/date (extract: min_amount=number, period="this_week"|"last_week"|"last_month")
  employee_spend    – an employee's expense total (extract: employee=name, period="this_quarter"|"last_month"|"this_month")
  upcoming_renewals – subscription renewals (extract: days=30|60|90)
  savings_total     – all savings identified
  overview_brief    – user wants a weekly summary, status update, or Monday brief
  general           – asking for data/metrics that require querying the Postgres database
  conversation      – general chit-chat, hello, needing help, non-data queries, personal assistant queries

Return ONLY a JSON object: {{"intent":"...","vendor":null,"tool":null,"employee":null,"min_amount":0,"period":"last_month","days":30}}
"""

_RESPONSE_PROMPT = """
You are Celsius, a friendly and highly capable personal AI assistant for a startup founder via iMessage.

Rules:
- Be conversational, helpful, and natural—as if you are their personal chief of staff texting them.
- Present data clearly, but wrap it in a friendly, engaging tone. 
- You can use greetings ("Sure!", "Here is the data") and natural sign-offs ("Let me know if you need anything else!").
- Do not be robotic or overly terse. Be warmly professional.
- Whenever appropriate, conclude by asking if there's any other help they need in the meantime.
- IF responding to an OVERVIEW BRIEF, strongly mimic this exact markdown format:
   Monday brief.
   💰 Spend: $Xk last week (±X% vs prior). 
   🔍 Found: X new SaaS ([vendors])
   ⚠️ Attention: X renewals this week ($Xk total).
   ✅ Handled for you: X actions. Total saved: $X.

Conversation Context:
{context}

Question: {question}
Data: {data}
"""


async def build_final_prompt(company_id: str, chat_id: str, question: str) -> str:
    """Assembles the stateful system prompt combining memory, history, and machines."""
    # 1. Short-term history
    history = await get_chat_history(chat_id)
    history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history]) if history else "No previous messages."
    
    # 2. Long-term memory (RAG)
    memories = await get_relevant_memories(question, company_id)
    memory_text = "\n".join([f"• {m['content']}" for m in memories]) if memories else "No relevant past events."
    
    # 3. Active Machines
    resp = (
        get_supabase()
        .table("active_machines")
        .select("vendor, status")
        .eq("company_id", company_id)
        .in_("status", ["running", "sleeping"])
        .execute()
    )
    machines = resp.data or []
    machines_text = "\n".join([f"- Negotiating {m['vendor']} ({m['status']})" for m in machines]) if machines else "None"
    
    return f"""
============= CONTEXT STRINGS =============
[ACTIVE MACHINES]
{machines_text}

[RELEVANT MEMORIES]
{memory_text}

[RECENT CHAT HISTORY]
{history_text}

[CURRENT MESSAGE]
USER: {question}
==========================================="""



async def _classify(question: str, api_key: str) -> dict[str, Any]:
    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    resp = await runner.run(
        input=_INTENT_PROMPT.format(question=question),
        model="anthropic/claude-haiku-4-5",
        max_tokens=150,
        instructions="Return only valid JSON. No markdown.",
    )
    raw = (resp.final_output or "").strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"intent": "general"}


async def _format_response(question: str, data: Any, api_key: str, context: str = "") -> str:
    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    preview = json.dumps(data, default=str)[:800]
    resp = await runner.run(
        input=_RESPONSE_PROMPT.format(question=question, data=preview, context=context),
        model="anthropic/claude-haiku-4-5",
        max_tokens=120,
        instructions=FLUX_PERSONA,
    )
    return (resp.final_output or "").strip()


async def _openai_chat_fallback(question: str, context: str) -> str:
    """Uses OpenAI generic capabilities to answer questions outside domain."""
    import os
    from openai import AsyncOpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "I'm sorry, I don't have the answer to that, and my OpenAI API keys are not configured to fall back to general knowledge!"
    
    client = AsyncOpenAI(api_key=api_key)
    prompt = f"""
{FLUX_PERSONA}

You are handling a conversational fallback. The user either asked a question not related to their exact internal databases, or started a general chat. Answer naturally using your broad AI knowledge.

{context}
"""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question}
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"I tried checking OpenAI, but couldn't reach it: {e}"


async def _fallback_flux_query(company_id: str, question: str, api_key: str) -> Optional[str]:
    """Generate SQL via Dedalus, execute via flux_query RPC."""
    today = datetime.now(timezone.utc).date().isoformat()
    schema_hint = (
        f"Postgres schema (company_id='{company_id}', today={today}): "
        "transactions(merchant,amount,pillar,created_at,savings_identified,submitted_by,employee_id), "
        "employees(name,email), seat_usage(tool,is_dormant,last_active_date), "
        "ai_usage(vendor,model,total_cost,week_start), "
        "subscription_renewals(vendor,renewal_date,current_monthly_cost), "
        "policy_actions(action_type,entity_name,amount,executed_at)"
    )
    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    sql_resp = await runner.run(
        input=f"Write a Postgres SELECT to answer: {question}\n{schema_hint}",
        model="anthropic/claude-haiku-4-5",
        max_tokens=300,
        instructions="Return only a Postgres SELECT statement. No markdown. No explanation.",
    )
    sql = (sql_resp.final_output or "").strip().strip("```sql").strip("```").strip()
    if not sql.upper().startswith("SELECT"):
        return None
    try:
        result = get_supabase().rpc("flux_query", {"query_sql": sql}).execute()
        rows = result.data or []
        # Not injecting the heavy context into format response here to save tokens on trivial SQL fallbacks
        return await _format_response(question, rows, api_key, context="")
    except Exception as e:
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

async def ask_anything(question: str, company_id: str) -> str:
    """Answer a natural-language question. Returns a founder-ready string."""
    import time
    start = time.monotonic()

    # Cache check
    cached = await asyncio.to_thread(_cache_read, company_id, question)
    if cached:
        return cached

    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        return "DEDALUS_API_KEY not set."

    # Provide context building (dummy chat_id is OK if ask_anything is not passed the phone number)
    # the overarching history is captured in main.py, but we build the prompt context here for intent/generation.
    context = await build_final_prompt(company_id, os.getenv("IMESSAGE_FOUNDER_PHONE", "founder"), question)

    # Classify with context injected into the question
    params = await _classify(context + "\n\n" + question, api_key)
    intent = params.get("intent", "general")
    period = params.get("period") or "last_month"

    # Map period to a since timestamp
    since_map = {
        "last_month": _ago(30),
        "this_month": _month_start(),
        "last_week": _ago(7),
        "this_week": _ago(7),
        "this_quarter": _quarter_start(),
        "last_quarter": _ago(90),
    }
    since = since_map.get(period, _ago(30))

    data: Any = None

    if intent == "ai_spend_total":
        data = await asyncio.to_thread(_run_ai_spend_total, company_id, since)

    elif intent == "inactive_seats":
        tool = params.get("tool")
        data = await asyncio.to_thread(_run_inactive_seats, company_id, tool)

    elif intent == "cancel_savings":
        vendor = params.get("vendor") or ""
        data = await asyncio.to_thread(_run_cancel_savings, company_id, vendor)

    elif intent == "recent_charges":
        min_amt = float(params.get("min_amount") or 0)
        data = await asyncio.to_thread(_run_recent_charges, company_id, min_amt, since)

    elif intent == "employee_spend":
        employee = params.get("employee") or ""
        data = await asyncio.to_thread(_run_employee_spend, company_id, employee, since)

    elif intent == "upcoming_renewals":
        days = int(params.get("days") or 30)
        data = await asyncio.to_thread(_run_upcoming_renewals, company_id, days)

    elif intent == "policy_actions":
        data = await asyncio.to_thread(_run_policy_actions, company_id, since)

    elif intent == "savings_total":
        data = await asyncio.to_thread(_run_savings_total, company_id)

    elif intent == "overview_brief":
        data = await asyncio.to_thread(_run_overview_brief, company_id)

    elif intent == "conversation":
        # Bypass SQL entirely for generic chat
        pass

    else:
        answer = await _fallback_flux_query(company_id, question, api_key)
        if answer:
            await asyncio.to_thread(_cache_write, company_id, question, answer)
            elapsed = round((time.monotonic() - start) * 1000)
            return answer

    # If it was a conversation, matched intent, or SQL fallback failed, drop through and generate conversational response
    if data is None:
        answer = await _openai_chat_fallback(question, context=context)
    else:
        answer = await _format_response(question, data, api_key, context=context)
        
    await asyncio.to_thread(_cache_write, company_id, question, answer)

    elapsed = round((time.monotonic() - start) * 1000)
    _ = elapsed  # available for logging if needed
    return answer
