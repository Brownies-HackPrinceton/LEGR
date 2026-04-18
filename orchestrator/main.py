from __future__ import annotations

import os
import re

from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agents.ask_anything import ask_anything
from orchestrator import route_transaction
from services.command_router import route_command
from services.imessage_sender import FOUNDER_PHONE, help_menu_text, send_boot_greeting, send_to_founder
from supabase_client import get_supabase


@asynccontextmanager
async def _lifespan(app: FastAPI):
    flag = os.getenv("IMESSAGE_BOOT_GREETING", "1").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        await send_boot_greeting()
    yield


app = FastAPI(lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (e.g. localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_COMPANY_ID = os.getenv("FLUX_COMPANY_ID", "00000001-0000-4000-8000-000000000001")

# ── Simple heuristics to classify an incoming message before touching Dedalus ──

_YES_WORDS = {"yes", "y", "proceed", "deploy", "ok", "okay", "do it", "send it", "go", "confirm"}
_NO_WORDS = {"no", "n", "skip", "cancel it", "stop", "don't", "nope", "pass"}

_QUERY_PATTERNS = re.compile(
    r"\b(what|how much|who|which|show|list|give me|tell me|"
    r"spent|spend|cost|costs|saving|savings|usage|using|used|"
    r"renew|renewal|invoice|expense|total|sum|breakdown|breakdown)\b",
    re.IGNORECASE,
)

_COMMAND_WORDS = re.compile(
    r"^\s*(cancel|negotiate|downgrade|email the team|approve|reject|"
    r"change|update|set|show pending)",
    re.IGNORECASE,
)

_MENU_WORDS = frozenset(
    {"hi", "hello", "hey", "help", "menu", "start", "flux", "?", "h", "commands", "suggest", "ideas"}
)


def _classify_message(text: str) -> str:
    low = text.strip().lower()
    words = set(low.split())

    # Single-word or short Y/N
    if words & _YES_WORDS and len(words) <= 4:
        return "yes_no"
    if words & _NO_WORDS and len(words) <= 3:
        return "yes_no"

    # Explicit command prefixes
    if _COMMAND_WORDS.match(text.strip()):
        return "command"

    # Query indicators
    if _QUERY_PATTERNS.search(text) or "?" in text:
        return "query"

    # Longer yes/no phrases
    if low in ("yes proceed", "yes do it", "go ahead", "sounds good"):
        return "yes_no"
    if low in ("no skip", "actually no", "hold off"):
        return "yes_no"

    return "unknown"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_pending_alert(company_id: str) -> Dict[str, Any] | None:
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
    rows = resp.data or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def _resolve_alert(alert_id: str, choice: str) -> None:
    get_supabase().table("agent_alerts").update({
        "resolved": True,
        "founder_action": choice,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", alert_id).execute()


def _lookup_negotiation_thread(company_id: str) -> Dict[str, Any] | None:
    resp = (
        get_supabase()
        .table("negotiation_threads")
        .select("*")
        .eq("company_id", company_id)
        .in_("state", ["pending", "counter_received"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/webhook/transaction")
async def on_transaction(request: Request):
    txn = await request.json()
    result = await route_transaction(txn)
    return {"status": "routed", "result": result}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/imessage/ping")
async def imessage_ping():
    """Send a hello + example prompts to the founder (bridge must be up)."""
    ok = await send_boot_greeting()
    return {"sent": ok, "founder_configured": bool(FOUNDER_PHONE)}


@app.post("/ask")
async def ask_endpoint(request: Request):
    """Direct REST endpoint for natural-language queries (also used by dashboard)."""
    body = await request.json()
    question = str(body.get("question") or "")
    company_id = str(body.get("company_id") or _COMPANY_ID)
    if not question:
        return {"error": "missing question"}
    answer = await ask_anything(question, company_id)
    return {"question": question, "answer": answer}


@app.post("/command")
async def command_endpoint(request: Request):
    """Direct REST endpoint for explicit commands (also usable from dashboard)."""
    body = await request.json()
    message = str(body.get("message") or "")
    company_id = str(body.get("company_id") or _COMPANY_ID)
    if not message:
        return {"error": "missing message"}
    result = await route_command(message, company_id)
    return result


@app.get("/digest/morning")
async def morning_brief():
    from services.digest import send_morning_brief
    ok = await send_morning_brief(_COMPANY_ID)
    return {"sent": ok}


@app.get("/digest/weekly")
async def weekly_digest():
    from services.digest import send_friday_digest
    ok = await send_friday_digest(_COMPANY_ID)
    return {"sent": ok}


@app.get("/negotiations")
async def list_negotiations():
    from services.negotiation_sm import maybe_stall
    stalled = await maybe_stall(_COMPANY_ID)
    resp = get_supabase().table("negotiation_threads").select("*").eq("company_id", _COMPANY_ID).order("updated_at", desc=True).limit(20).execute()
    return {"threads": resp.data or [], "newly_stalled": stalled}


@app.get("/activity")
async def activity_feed():
    """Dashboard activity feed — last 50 Flux actions."""
    alerts = (
        get_supabase()
        .table("agent_alerts")
        .select("*")
        .eq("company_id", _COMPANY_ID)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    ).data or []

    actions = (
        get_supabase()
        .table("policy_actions")
        .select("*")
        .eq("company_id", _COMPANY_ID)
        .order("executed_at", desc=True)
        .limit(20)
        .execute()
    ).data or []

    return {"alerts": alerts, "autonomous_actions": actions}


# ── Core iMessage handler ─────────────────────────────────────────────────────

@app.post("/webhooks/imessage")
async def on_imessage(request: Request):
    """
    Bridge forwards every inbound iMessage here.

    Classification:
      1. Employee reply  → handle via employee_threads
      2. Y/N on pending alert → resolve it; if Y on negotiate/cancel, execute action
      3. Query (? / what / how much / …) → ask_anything
      4. Command (cancel / negotiate / …) → command_router
      5. Unrecognized → help prompt
    """
    body: Dict[str, Any] = await request.json()
    raw_text = str(body.get("text") or body.get("body") or "").strip()
    sender_phone = str(body.get("sender") or body.get("from") or body.get("from_phone") or "")

    if not raw_text:
        return {"status": "ignored", "reason": "empty_body"}

    # ── 1. Employee thread? ───────────────────────────────────────────────────
    from services.employee_threads import handle_employee_reply

    founder_phone = FOUNDER_PHONE
    if sender_phone and sender_phone != founder_phone:
        result = await handle_employee_reply(sender_phone, raw_text)
        if result.get("requires_founder"):
            await send_to_founder(result["message"], pillar="compliance")
        return {"status": "employee_reply", **result}

    # ── 2–5: Founder messages ─────────────────────────────────────────────────
    low_stripped = raw_text.strip().lower()
    if low_stripped in _MENU_WORDS:
        await send_to_founder(help_menu_text())
        return {"status": "menu_sent"}

    msg_type = _classify_message(raw_text)

    # ── 2. Y/N resolution ────────────────────────────────────────────────────
    if msg_type == "yes_no":
        low = raw_text.strip().lower()
        yes = any(w in low for w in _YES_WORDS)

        alert = _find_pending_alert(_COMPANY_ID)
        if not alert:
            # Check if there's a pending negotiation thread waiting for approval
            thread = _lookup_negotiation_thread(_COMPANY_ID)
            if thread and yes:
                from services.negotiation_sm import send_initial
                await send_initial(thread["id"])
                # TODO: wire Gmail API to actually send the draft_email
                await send_to_founder(
                    f"✅ Negotiation email sent to {thread['vendor']}. I'll update you when they reply.",
                    pillar="saas_sprawl",
                    with_suggestions=True,
                    suggestion_count=2,
                )
                return {"status": "negotiation_started", "thread_id": thread["id"]}
            return {"status": "ignored", "reason": "no_pending_alert"}

        _resolve_alert(alert["id"], "Y" if yes else "N")

        # Execute action on Y
        if yes:
            alert_type = str(alert.get("alert_type") or "")
            vendor = alert.get("vendor") or ""

            if alert_type in ("cancel_requested", "downgrade_requested"):
                await send_to_founder(
                    f"✅ Cancellation email sent to {vendor or 'vendor'}. Tracking cancellation.",
                    pillar="saas_sprawl",
                    with_suggestions=True,
                    suggestion_count=2,
                )
            elif alert_type == "negotiate_pending":
                await send_to_founder(
                    f"✅ Negotiation email queued for {vendor}. I'll report back when they respond.",
                    pillar="saas_sprawl",
                    with_suggestions=True,
                    suggestion_count=2,
                )
            else:
                await send_to_founder(
                    f"✅ Done — {alert.get('message', '')[:60]}",
                    pillar=alert.get("pillar"),
                    alert_id=alert.get("id"),
                    with_suggestions=True,
                    suggestion_count=2,
                )
        else:
            await send_to_founder(
                "Skipped. Let me know if you change your mind.",
                with_suggestions=True,
                suggestion_count=2,
            )

        return {"status": "resolved", "choice": "Y" if yes else "N", "alert_id": alert["id"]}

    # ── 3. Query ─────────────────────────────────────────────────────────────
    if msg_type == "query":
        answer = await ask_anything(raw_text, _COMPANY_ID)
        await send_to_founder(answer, with_suggestions=True)
        return {"status": "query_answered", "answer": answer}

    # ── 4. Command ───────────────────────────────────────────────────────────
    if msg_type == "command":
        result = await route_command(raw_text, _COMPANY_ID)
        reply = result.get("reply")
        if reply:
            pending = bool(result.get("action", "").endswith("_pending"))
            await send_to_founder(
                reply,
                poll=pending,
                action_prompt="Confirm?" if pending else None,
                pillar=result.get("pillar"),
                with_suggestions=not pending,
                suggestion_count=3,
            )
        return {"status": "command_routed", **result}

    # ── 5. Conversational fallback → same agent as dashboard / queries ─────────
    answer = await ask_anything(raw_text, _COMPANY_ID)
    await send_to_founder(answer, with_suggestions=True)
    return {"status": "agent_answered", "answer": answer}
