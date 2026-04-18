from __future__ import annotations

import os
import random
from typing import Optional

import httpx

BRIDGE_URL = os.getenv("IMESSAGE_BRIDGE_URL", "http://127.0.0.1:3099")
FOUNDER_PHONE = (os.getenv("IMESSAGE_FOUNDER_PHONE") or "").strip()
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")

# Example prompts shown after agent replies (iMessage is the only UI).
ASK_SUGGESTIONS: tuple[str, ...] = (
    "What did we spend on AI last month?",
    "Which subscriptions renew in the next 30 days?",
    "Show charges over $500 this week",
    "How much savings have we found in total?",
    "Who has dormant seats on Linear?",
    "What did Flux run autonomously this week?",
    "negotiate with Notion",
    "show pending",
)


def suggestion_block(count: int = 3, *, exclude_substring: str | None = None) -> str:
    pool = list(ASK_SUGGESTIONS)
    if exclude_substring:
        low = exclude_substring.lower()
        pool = [s for s in pool if low not in s.lower()]
    if not pool:
        pool = list(ASK_SUGGESTIONS)
    random.shuffle(pool)
    picks = pool[: min(count, len(pool))]
    lines = "\n".join(f"• {s}" for s in picks)
    return f"\n\n— Try asking:\n{lines}"


def with_ask_suggestions(body: str, count: int = 3, *, exclude_substring: str | None = None) -> str:
    return f"{body.rstrip()}{suggestion_block(count, exclude_substring=exclude_substring)}"


def help_menu_text() -> str:
    return (
        "I'm Flux — ask in plain English about spend, renewals, seats, or say "
        "'show pending' for alerts. Y/N still works when I send an approval."
        + suggestion_block(4)
    )


def _dashboard_link(pillar: str, extra: str = "") -> str:
    routes = {
        "ai_spend": "/#/ai-spend",
        "saas_sprawl": "/#/saas-sprawl",
        "compliance": "/#/compliance",
    }
    path = routes.get(pillar, "/#/dashboard")
    qs = f"?{extra}" if extra else ""
    return f"{DASHBOARD_URL}{path}{qs}"


async def send_text(to: str, body: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{BRIDGE_URL}/send", json={"to": to, "text": body})
            return r.status_code == 200 and bool(r.json().get("ok"))
    except Exception:
        return False


async def send_boot_greeting() -> bool:
    """Hello + example prompts (no dashboard link)."""
    if not FOUNDER_PHONE:
        return False
    msg = (
        "Flux is live on this thread — I'll answer questions and ping you when "
        "transactions need a decision."
        + suggestion_block(4)
    )
    return await send_text(FOUNDER_PHONE, msg)


async def send_poll(to: str, question: str, options: Optional[list[str]] = None) -> bool:
    opts = options or ["Yes, proceed", "No, skip"]
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{BRIDGE_URL}/send_poll",
                json={"to": to, "question": question, "options": opts},
            )
            return r.status_code == 200 and bool(r.json().get("ok"))
    except Exception:
        return False


async def send_to_founder(
    body: str,
    *,
    poll: bool = False,
    action_prompt: Optional[str] = None,
    pillar: Optional[str] = None,
    alert_id: Optional[str] = None,
    with_suggestions: bool = False,
    suggestion_count: int = 3,
) -> bool:
    phone = FOUNDER_PHONE
    if not phone:
        return False

    text = body
    if with_suggestions and not poll:
        text = with_ask_suggestions(text, suggestion_count)

    # Append tap-through link for non-urgent, non-Y/N messages when pillar is known
    link_suffix = ""
    if pillar and not poll:
        extra = f"alert={alert_id}" if alert_id else ""
        link_suffix = f"\n\n{_dashboard_link(pillar, extra)}"

    if poll and action_prompt:
        return await send_poll(phone, f"🚨 {text}\n\n{action_prompt}{link_suffix}")
    return await send_text(phone, f"{text}{link_suffix}")


async def send_to_employee(phone: str, body: str) -> bool:
    return await send_text(phone, body)
