"""
Machine loop — the long-running entry point for a Dedalus Machine.

This is the `while True` process that:
  1. Boots, creates initial state, drafts & sends round-1 email
  2. Polls inbox every POLL_INTERVAL seconds
  3. When a reply arrives: classify → reason → draft counter → send → update state
  4. On terminal state: archive, update Supabase, notify founder, exit

Spawned as a subprocess by the orchestrator.

Usage:
  python -m machine.loop \\
    --vendor Cursor \\
    --price 480 \\
    --target-pct 25 \\
    --company-id 00000001-... \\
    --thread-id <uuid> \\
    --demo
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timezone

# Ensure the orchestrator dir is on the path (for imports when run as subprocess)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from machine.state import (
    NegotiationState,
    ThreadMessage,
    archive_state,
    append_log,
    load_state,
    machine_heartbeat_log,
    save_state,
    ensure_dirs,
)
from machine.inbox import IncomingEmail, create_inbox
from machine.outbox import send_email
from machine import reasoner

# Lazy import Supabase (may not be needed if running in demo-only)
_supabase = None

def _get_supabase():
    global _supabase
    if _supabase is None:
        try:
            from supabase_client import get_supabase
            _supabase = get_supabase()
        except Exception:
            _supabase = None
    return _supabase


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _register_machine(company_id: str, vendor: str, thread_id: str, state_path_str: str) -> str | None:
    """Register this Machine in active_machines. Returns machine_id."""
    sb = _get_supabase()
    if not sb:
        return None
    try:
        row = sb.table("active_machines").insert({
            "company_id": company_id,
            "type": "negotiation",
            "vendor": vendor,
            "thread_id": thread_id or None,
            "pid": os.getpid(),
            "state_path": state_path_str,
            "status": "running",
        }).execute()
        rows = row.data or []
        return rows[0]["id"] if rows else None
    except Exception as exc:
        print(f"  ⚠️  Failed to register machine: {exc}")
        return None


def _update_heartbeat(machine_id: str | None, status: str = "running") -> None:
    if not machine_id:
        return
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("active_machines").update({
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }).eq("id", machine_id).execute()
    except Exception:
        pass


def _close_machine(machine_id: str | None, outcome: str) -> None:
    if not machine_id:
        return
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("active_machines").update({
            "status": "closed",
            "outcome": outcome,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        }).eq("id", machine_id).execute()
    except Exception:
        pass


def _update_negotiation_thread(thread_id: str, patch: dict) -> None:
    """Update the negotiation_threads table in Supabase."""
    sb = _get_supabase()
    if not sb or not thread_id:
        return
    try:
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        sb.table("negotiation_threads").update(patch).eq("id", thread_id).execute()
    except Exception:
        pass


# ── Photon iMessage notifications ─────────────────────────────────────────────

async def _notify_founder(message: str, demo: bool = False) -> None:
    """Send a status update to the founder via Photon iMessage."""
    if demo:
        print(f"  💬 [iMessage] {message}")
        return
    try:
        from services.imessage_sender import send_to_founder
        await send_to_founder(message, pillar="saas_sprawl")
    except Exception as exc:
        print(f"  ⚠️  iMessage send failed: {exc}")


# ── Main loop ─────────────────────────────────────────────────────────────────

_SHUTDOWN = False

def _handle_signal(sig, frame):
    global _SHUTDOWN
    _SHUTDOWN = True
    print("\n  🛑 Shutdown signal received, finishing current cycle...")


async def run_machine(
    vendor: str,
    price: float,
    target_pct: float,
    company_id: str,
    thread_id: str = "",
    vendor_email: str = "",
    demo: bool = False,
    poll_interval: int = 10,
) -> None:
    """Main machine loop."""
    ensure_dirs()

    # Resolve vendor email
    if not vendor_email:
        vendor_email = f"renewals@{vendor.lower().replace(' ', '')}.com"

    print(f"\n{'='*60}")
    print(f"  🤖 DEDALUS MACHINE — Negotiation Agent")
    print(f"  Vendor:  {vendor}")
    print(f"  Price:   ${price:,.0f}/mo")
    print(f"  Target:  {target_pct}% discount")
    print(f"  Mode:    {'DEMO' if demo else 'PRODUCTION'}")
    print(f"  Poll:    every {poll_interval}s")
    print(f"{'='*60}\n")

    # ── Load or create state ──────────────────────────────────────────────────
    state = load_state(vendor)
    if state is None:
        subject = f"{vendor} renewal — pricing adjustment"
        state = NegotiationState(
            vendor=vendor,
            vendor_email=vendor_email,
            original_price=price,
            target_discount_pct=target_pct,
            floor_discount_pct=5.0,
            company_id=company_id,
            thread_id=thread_id,
            subject_line=subject,
        )
        save_state(state)
        append_log(vendor, f"Machine created: target={target_pct}%, price=${price}")

    # Register in Supabase
    machine_id = _register_machine(company_id, vendor, thread_id, str(save_state(state)))
    state.machine_id = machine_id or ""

    # Create inbox
    inbox = create_inbox(demo=demo, vendor=vendor)

    # ── Round 0: Draft & send initial email ───────────────────────────────────
    if state.current_round == 0:
        print("  📝 Drafting initial negotiation email...")
        append_log(vendor, "Drafting initial email via reasoner")

        initial_email = await reasoner.draft_initial_email(state)

        print(f"  📧 Sending to {vendor_email}...")
        sent = send_email(
            to=vendor_email,
            subject=state.subject_line,
            body=initial_email,
            vendor=vendor,
            round_num=1,
            demo=demo,
        )

        state.current_round = 1
        state.status = "waiting_reply"
        state.thread.append(ThreadMessage(
            direction="outbound",
            body=initial_email,
            timestamp=datetime.now(timezone.utc).isoformat(),
            round_num=1,
        ))
        state.leverage_used.append("competitive_alternatives")
        state.leverage_used.append("annual_commitment")
        save_state(state)

        _update_heartbeat(machine_id)
        _update_negotiation_thread(thread_id, {
            "state": "waiting_reply",
            "draft_email": initial_email,
            "turn_count": 1,
        })

        await _notify_founder(
            f"📧 Negotiation email sent to {vendor}. Monitoring for their reply...",
            demo=demo,
        )
        print(f"  ✅ Round 1 email sent. Entering poll loop.\n")

    # ── Poll loop ─────────────────────────────────────────────────────────────
    terminal_states = {"closed_won", "closed_lost", "escalated"}

    while state.status not in terminal_states and not _SHUTDOWN:
        machine_heartbeat_log(f"{vendor}: alive, round={state.current_round}, status={state.status}")
        _update_heartbeat(machine_id, "sleeping")

        # Sleep (interruptible)
        print(f"  💤 Sleeping {poll_interval}s... (round {state.current_round}, status: {state.status})")
        for _ in range(poll_interval):
            if _SHUTDOWN:
                break
            await asyncio.sleep(1)

        if _SHUTDOWN:
            break

        _update_heartbeat(machine_id, "running")

        # Poll inbox
        replies = inbox.poll(vendor, state.subject_line)

        if not replies:
            print(f"  📭 No new replies. Continuing...")
            continue

        # Process each reply
        for reply in replies:
            print(f"\n  📬 New reply from {reply.from_addr}!")
            print(f"     Subject: {reply.subject}")
            print(f"     Body: {reply.body[:100]}...")

            state.thread.append(ThreadMessage(
                direction="inbound",
                body=reply.body,
                timestamp=reply.received_at,
                round_num=state.current_round,
            ))

            # Classify
            print("  🧠 Classifying reply...")
            classification = await reasoner.classify_reply(reply.body, state)
            print(f"     → {classification.kind} (offer: {classification.offer_pct}%, confidence: {classification.confidence})")

            state.current_offer_pct = classification.offer_pct
            state.reasoning_log.append(
                f"Round {state.current_round}: {classification.kind} "
                f"(offer={classification.offer_pct}%) — {classification.reasoning}"
            )

            # Decide next move
            print("  🎯 Deciding next move...")
            next_move = await reasoner.draft_next_move(state, classification)
            print(f"     → Action: {next_move.action} (ask: {next_move.our_ask_pct}%)")
            print(f"     → Reasoning: {next_move.reasoning}")

            append_log(vendor, f"Round {state.current_round}: {classification.kind} → {next_move.action}")

            # Execute the move
            if next_move.action == "accept":
                pct = classification.offer_pct or state.target_discount_pct
                new_price = state.original_price * (1 - pct / 100)
                savings = state.original_price - new_price

                state.status = "closed_won"
                state.closed_at = datetime.now(timezone.utc).isoformat()
                save_state(state)

                _update_negotiation_thread(thread_id, {
                    "state": "closed_won",
                    "current_offer_pct": pct,
                    "turn_count": state.current_round,
                    "closed_at": state.closed_at,
                    "outcome_notes": f"Won at {pct}%. New: ${new_price:,.0f}/mo. Saved ${savings:,.0f}/mo.",
                })

                msg = (
                    f"✅ {vendor} closed at {pct}% discount!\n"
                    f"New price: ${new_price:,.0f}/mo (was ${state.original_price:,.0f})\n"
                    f"Savings: ${savings:,.0f}/mo (${savings * 12:,.0f}/yr)\n"
                    f"Rounds: {state.current_round}"
                )
                await _notify_founder(msg, demo=demo)
                print(f"\n  🎉 DEAL WON: {msg}")

            elif next_move.action == "send_counter":
                state.current_round += 1
                state.status = "counter_sent"
                state.thread.append(ThreadMessage(
                    direction="outbound",
                    body=next_move.email_text,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    round_num=state.current_round,
                    classification="counter",
                ))
                save_state(state)

                send_email(
                    to=vendor_email,
                    subject=f"Re: {state.subject_line}",
                    body=next_move.email_text,
                    vendor=vendor,
                    round_num=state.current_round,
                    demo=demo,
                )

                _update_negotiation_thread(thread_id, {
                    "state": "counter_sent",
                    "current_offer_pct": classification.offer_pct,
                    "turn_count": state.current_round,
                    "draft_email": next_move.email_text,
                    "latest_vendor_reply": reply.body[:500],
                })

                pct = classification.offer_pct or 0
                await _notify_founder(
                    f"🔄 {vendor} Round {state.current_round}: "
                    f"vendor offered {pct}%, countering at {next_move.our_ask_pct}%.",
                    demo=demo,
                )
                # Reset status to waiting
                state.status = "waiting_reply"
                save_state(state)

                print(f"  📧 Counter sent (round {state.current_round})")

            elif next_move.action == "walk_away":
                state.status = "closed_lost"
                state.closed_at = datetime.now(timezone.utc).isoformat()
                save_state(state)

                _update_negotiation_thread(thread_id, {
                    "state": "closed_lost",
                    "turn_count": state.current_round,
                    "closed_at": state.closed_at,
                    "outcome_notes": "Vendor declined. Machine walked away.",
                })

                await _notify_founder(
                    f"❌ {vendor} declined our discount request after {state.current_round} rounds. "
                    f"Want to cancel the subscription or try a different approach?",
                    demo=demo,
                )
                print(f"\n  ❌ DEAL LOST: Vendor declined.")

            elif next_move.action == "escalate":
                state.status = "escalated"
                save_state(state)

                _update_negotiation_thread(thread_id, {
                    "state": "stalled",
                    "turn_count": state.current_round,
                    "outcome_notes": f"Escalated after {state.current_round} rounds.",
                })

                await _notify_founder(
                    f"⚠️ {vendor} negotiation stuck after {state.current_round} rounds. "
                    f"Needs your direct intervention.",
                    demo=demo,
                )
                print(f"\n  ⚠️  ESCALATED: Too many rounds without resolution.")

            elif next_move.action == "wait":
                print(f"  ⏳ Vendor is stalling. Will check again next cycle.")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if state.status in terminal_states:
        archived = archive_state(vendor)
        if archived:
            print(f"\n  📁 State archived to {archived}")
        _close_machine(machine_id, state.status)
        append_log(vendor, f"Machine exited: {state.status}")
    else:
        # Shutdown signal — mark as sleeping, don't archive
        _update_heartbeat(machine_id, "sleeping")
        append_log(vendor, "Machine paused by shutdown signal")

    print(f"\n  🏁 Machine exited. Final status: {state.status}")
    print(f"{'='*60}\n")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    parser = argparse.ArgumentParser(description="Dedalus Machine — Negotiation Agent")
    parser.add_argument("--vendor", required=True, help="Vendor name (e.g., Cursor)")
    parser.add_argument("--price", type=float, required=True, help="Current monthly price in $")
    parser.add_argument("--target-pct", type=float, required=True, help="Target discount percentage")
    parser.add_argument("--company-id", default="00000001-0000-4000-8000-000000000001")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--vendor-email", default="")
    parser.add_argument("--demo", action="store_true", help="Use canned replies instead of IMAP")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between inbox polls")

    args = parser.parse_args()

    asyncio.run(run_machine(
        vendor=args.vendor,
        price=args.price,
        target_pct=args.target_pct,
        company_id=args.company_id,
        thread_id=args.thread_id,
        vendor_email=args.vendor_email,
        demo=args.demo,
        poll_interval=args.poll_interval,
    ))


if __name__ == "__main__":
    main()
