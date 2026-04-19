from __future__ import annotations

import os
from typing import Optional

import httpx

BRIDGE_URL = os.getenv("IMESSAGE_BRIDGE_URL", "http://127.0.0.1:3099")
FOUNDER_PHONE = (os.getenv("IMESSAGE_FOUNDER_PHONE") or "").strip()
_COMPANY_ID = os.getenv("FLUX_COMPANY_ID", "00000001-0000-4000-8000-000000000001")


async def send_text(to: str, body: str) -> bool:
    try:
        from services.memory import save_chat_message
        await save_chat_message(to, "assistant", body, _COMPANY_ID)
        
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{BRIDGE_URL}/send", json={"to": to, "text": body})
            return r.status_code == 200 and bool(r.json().get("ok"))
    except Exception as e:
        print(f"Failed to send text to {to}: {e}")
        return False


async def send_boot_greeting() -> bool:
    if not FOUNDER_PHONE:
        return False
    msg = (
        "Celsius is watching your spend. Ask me anything — "
        "what you burned on AI, which SaaS seats are dormant, upcoming renewals. "
        "I'll ping you when something needs a decision."
    )
    return await send_text(FOUNDER_PHONE, msg)


def help_menu_text() -> str:
    return (
        "Ask in plain English:\n"
        "• what did we spend on AI last month\n"
        "• which subs renew in 30 days\n"
        "• who has dormant seats on Linear\n"
        "• cancel Notion / negotiate with Figma\n"
        "• show pending\n\n"
        "Reply Y or N when I send an approval."
    )


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

    if poll and action_prompt:
        return await send_poll(phone, f"{body}\n\n{action_prompt}")
    return await send_text(phone, body)


async def send_to_employee(phone: str, body: str) -> bool:
    return await send_text(phone, body)
