"""
Machine reasoner — Dedalus + Claude for negotiation intelligence.

Classifies vendor replies (accept / counter / reject / stall) and drafts
counter-offers using full negotiation state context. This is where
Claude Sonnet's reasoning is load-bearing — it needs to understand leverage,
past offers, and negotiation dynamics.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from machine.state import NegotiationState, ThreadMessage, append_log


# ── Types ─────────────────────────────────────────────────────────────────────

ReplyClass = Literal["accept", "counter", "reject", "stall", "irrelevant"]
ActionKind = Literal["send_counter", "accept", "walk_away", "escalate", "wait"]


@dataclass
class Classification:
    kind: ReplyClass
    offer_pct: Optional[float]
    confidence: float
    reasoning: str


@dataclass
class NextMove:
    action: ActionKind
    email_text: str
    our_ask_pct: float
    reasoning: str


# ── Heuristic classifier (fast, no LLM) ──────────────────────────────────────

def _heuristic_classify(reply_text: str) -> Classification:
    """Quick regex-based classification — used as fallback or first pass."""
    low = reply_text.lower()

    # Extract percentage offers
    pcts = re.findall(r"(\d{1,2})%", reply_text)
    offer_pct = float(pcts[0]) if pcts else None

    # Acceptance signals
    accept_words = ("confirm", "agreed", "done", "proceed", "accept", "match your ask", "we've agreed")
    if any(w in low for w in accept_words) and offer_pct is not None:
        return Classification(
            kind="accept",
            offer_pct=offer_pct,
            confidence=0.85,
            reasoning=f"Vendor used acceptance language with {offer_pct}% offer",
        )

    # Rejection signals
    reject_words = ("unable", "cannot", "won't", "can't offer", "no discount", "best price", "not possible", "standardized")
    if any(w in low for w in reject_words):
        return Classification(
            kind="reject",
            offer_pct=offer_pct,
            confidence=0.80,
            reasoning="Vendor used rejection language",
        )

    # Counter-offer (has a percentage but no acceptance)
    if offer_pct is not None:
        return Classification(
            kind="counter",
            offer_pct=offer_pct,
            confidence=0.75,
            reasoning=f"Vendor counter-offered at {offer_pct}%",
        )

    # Stall (acknowledges but no concrete number)
    stall_words = ("reviewing", "discuss internally", "get back to you", "escalate", "let me check")
    if any(w in low for w in stall_words):
        return Classification(
            kind="stall",
            offer_pct=None,
            confidence=0.60,
            reasoning="Vendor is stalling / needs internal review",
        )

    return Classification(
        kind="irrelevant",
        offer_pct=None,
        confidence=0.30,
        reasoning="Could not classify vendor reply",
    )


# ── LLM-powered classifier ───────────────────────────────────────────────────

async def classify_reply(reply_text: str, state: NegotiationState) -> Classification:
    """
    Classify a vendor reply using Dedalus + Claude.
    Falls back to heuristics if no API key.
    """
    # Always start with heuristics for speed
    heuristic = _heuristic_classify(reply_text)

    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        append_log(state.vendor, f"REASONER: no API key, using heuristic: {heuristic.kind}")
        return heuristic

    try:
        from dedalus_labs import AsyncDedalus, DedalusRunner

        client = AsyncDedalus(api_key=api_key)
        runner = DedalusRunner(client)

        prompt = f"""Classify this vendor reply in a SaaS renewal negotiation.

CONTEXT:
- Vendor: {state.vendor}
- Our target: {state.target_discount_pct}% discount
- Our floor (minimum acceptable): {state.floor_discount_pct}%
- Current round: {state.current_round}
- Their previous offer: {state.current_offer_pct or 'none yet'}%

VENDOR REPLY:
{reply_text}

Classify as EXACTLY ONE of:
- accept: vendor accepted our terms or offered at/above our target
- counter: vendor made a concrete counter-offer (has a specific %)
- reject: vendor declined / said no discount possible
- stall: vendor is delaying / needs internal review
- irrelevant: auto-reply, unrelated content

OUTPUT FORMAT (JSON only, no markdown):
{{"kind": "accept|counter|reject|stall|irrelevant", "offer_pct": <number or null>, "confidence": <0-1>, "reasoning": "<1 sentence>"}}
"""
        resp = await runner.run(
            input=prompt,
            model="anthropic/claude-haiku-4-5",
            max_tokens=200,
        )
        raw = (resp.final_output or "").strip()

        # Parse JSON from response
        import json
        # Try to extract JSON from response
        json_match = re.search(r"\{[^}]+\}", raw)
        if json_match:
            data = json.loads(json_match.group())
            return Classification(
                kind=data.get("kind", heuristic.kind),
                offer_pct=data.get("offer_pct"),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
            )

    except Exception as exc:
        append_log(state.vendor, f"REASONER classify error: {exc}")

    return heuristic


# ── Counter-offer drafter ─────────────────────────────────────────────────────

async def draft_next_move(state: NegotiationState, classification: Classification) -> NextMove:
    """
    Given current state + classification, decide and draft the next move.
    Uses Claude Sonnet for the actual email drafting (tone matters).
    """
    vendor = state.vendor
    target = state.target_discount_pct
    floor = state.floor_discount_pct
    offer = classification.offer_pct
    current_round = state.current_round

    # ── Terminal states ───────────────────────────────────────────────────────

    if classification.kind == "accept":
        return NextMove(
            action="accept",
            email_text="",
            our_ask_pct=offer or target,
            reasoning=f"Vendor accepted at {offer}%. Deal closed.",
        )

    if classification.kind == "reject":
        return NextMove(
            action="walk_away",
            email_text="",
            our_ask_pct=target,
            reasoning="Vendor firmly declined. Recommending walk-away or escalation.",
        )

    if current_round >= 4:
        return NextMove(
            action="escalate",
            email_text="",
            our_ask_pct=target,
            reasoning=f"4+ rounds with no resolution. Escalating to founder for manual intervention.",
        )

    if classification.kind == "stall":
        return NextMove(
            action="wait",
            email_text="",
            our_ask_pct=target,
            reasoning="Vendor is reviewing internally. Will check again next cycle.",
        )

    # ── Counter-offer: draft response ─────────────────────────────────────────

    # Calculate our counter-ask: split the difference, but never below target
    if offer is not None and offer >= target:
        # They met our target — accept
        return NextMove(
            action="accept",
            email_text="",
            our_ask_pct=offer,
            reasoning=f"Vendor offered {offer}% which meets/exceeds our {target}% target.",
        )

    our_ask = target  # Always push for our target
    if offer is not None and offer > 0:
        # If they're close, hold firm; if far, be slightly flexible
        gap = target - offer
        if gap <= 3:
            our_ask = target  # Hold firm, we're close
        else:
            our_ask = target  # Still hold firm — we have leverage

    # Build leverage context
    leverage_context = ""
    if state.leverage_used:
        leverage_context = f"\nLeverage already cited (don't repeat): {', '.join(state.leverage_used)}"

    available_leverage = []
    if "competitive_alternatives" not in state.leverage_used:
        available_leverage.append("competitive alternatives exist")
    if "budget_constraints" not in state.leverage_used:
        available_leverage.append("strict 2026 budget constraints")
    if "annual_commitment" not in state.leverage_used:
        available_leverage.append("willingness to commit to annual if discount is right")
    if "seat_reduction" not in state.leverage_used:
        available_leverage.append("will reduce seats if price doesn't improve")

    leverage_str = ", ".join(available_leverage[:2]) if available_leverage else "genuine cost sensitivity"

    # Try LLM drafting
    api_key = os.getenv("DEDALUS_API_KEY")
    email_text: str

    if api_key:
        try:
            from dedalus_labs import AsyncDedalus, DedalusRunner

            client = AsyncDedalus(api_key=api_key)
            runner = DedalusRunner(client)

            thread_history = "\n".join(
                f"[{'US' if m.direction == 'outbound' else 'VENDOR'}] {m.body[:200]}"
                for m in state.thread[-4:]  # Last 4 messages for context
            )

            prompt = f"""Draft a counter-offer reply in a SaaS renewal negotiation.

CONTEXT:
- Vendor: {vendor}
- Original price: ${state.original_price:,.0f}/mo
- Their current offer: {offer}% discount (${state.original_price * (1 - (offer or 0)/100):,.0f}/mo)
- Our target: {target}% discount (${state.original_price * (1 - target/100):,.0f}/mo)
- This is round {current_round + 1}
- New leverage to use: {leverage_str}
{leverage_context}

THREAD HISTORY:
{thread_history}

INSTRUCTIONS:
1. Be professional, concise (2 short paragraphs max)
2. Acknowledge their offer but push for {our_ask}%
3. Cite new leverage: {leverage_str}
4. Make it clear this is the number we need to renew
5. Don't be aggressive — firm but respectful
"""
            resp = await runner.run(
                input=prompt,
                model="anthropic/claude-sonnet-4-6",
                max_tokens=400,
            )
            email_text = (resp.final_output or "").strip()

        except Exception as exc:
            append_log(vendor, f"REASONER draft error: {exc}")
            email_text = ""

    else:
        email_text = ""

    # Fallback email
    if not email_text:
        new_price = state.original_price * (1 - our_ask / 100)
        email_text = (
            f"Hi {vendor} team,\n\n"
            f"Thanks for the {offer}% offer. We appreciate the movement, but "
            f"we need to reach {our_ask}% (${new_price:,.0f}/mo) to commit to renewal. "
            f"We're comparing {leverage_str} and need this number to make it work.\n\n"
            f"Can you make {our_ask}% happen? Happy to sign an annual term today if so.\n\n"
            f"Thanks"
        )

    # Track which leverage we used
    new_leverage = []
    if "competitive" in leverage_str.lower():
        new_leverage.append("competitive_alternatives")
    if "budget" in leverage_str.lower():
        new_leverage.append("budget_constraints")
    if "annual" in leverage_str.lower():
        new_leverage.append("annual_commitment")
    if "seat" in leverage_str.lower() or "reduce" in leverage_str.lower():
        new_leverage.append("seat_reduction")

    return NextMove(
        action="send_counter",
        email_text=email_text,
        our_ask_pct=our_ask,
        reasoning=f"Counter at {our_ask}% (round {current_round + 1}), leveraging: {leverage_str}",
    )


# ── Initial email drafter ─────────────────────────────────────────────────────

async def draft_initial_email(state: NegotiationState) -> str:
    """Draft the first outbound negotiation email."""
    vendor = state.vendor
    price = state.original_price
    target = state.target_discount_pct
    new_price = price * (1 - target / 100)

    api_key = os.getenv("DEDALUS_API_KEY")
    if api_key:
        try:
            from dedalus_labs import AsyncDedalus, DedalusRunner

            client = AsyncDedalus(api_key=api_key)
            runner = DedalusRunner(client)

            prompt = f"""Draft a renewal negotiation email to {vendor}.
Current price: ${price:,.0f}/mo
Target: {target}% discount (${new_price:,.0f}/mo)

Write a direct, professional email from a startup founder. 2-3 short paragraphs.
Cite competitive pressure, cost sensitivity, and willingness to commit to annual if discount is granted.
Include a clear ask. No fluff.
"""
            resp = await runner.run(
                input=prompt,
                model="anthropic/claude-sonnet-4-6",
                max_tokens=400,
            )
            text = (resp.final_output or "").strip()
            if text:
                return text
        except Exception as exc:
            append_log(vendor, f"REASONER initial draft error: {exc}")

    # Fallback
    return (
        f"Subject: {vendor} renewal — pricing adjustment\n\n"
        f"Hi {vendor} team,\n\n"
        f"We're reviewing renewals across our stack and need to bring {vendor} "
        f"in line with our 2026 budget. We're currently at ${price:,.0f}/mo; "
        f"we can renew on an annual term if you can offer a {target}% discount "
        f"(~${new_price:,.0f}/mo).\n\n"
        f"If that's workable, please send the updated quote. If not, we'll "
        f"likely need to right-size or consider alternatives.\n\n"
        f"Thanks"
    )
