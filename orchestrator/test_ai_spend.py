"""
Run: cd orchestrator && python test_ai_spend.py
Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY (flux/.env). DEDALUS_API_KEY optional — without it,
the agent still uses seed history and a deterministic fallback narrative.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / "flux" / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from agents.ai_spend import ai_spend_agent

ACME_COMPANY_ID = "00000001-0000-4000-8000-000000000001"


def _message_covers_seed(msg: str) -> bool:
    """Seed row: 38K Opus calls, invoice_classification, Haiku saves $2,840/mo (flexible for LLM wording)."""
    lower = msg.lower()
    checks = [
        "opus" in lower or "claude-opus" in lower,
        "haiku" in lower or "claude-haiku" in lower,
        "2840" in msg or "2,840" in msg,
        bool(re.search(r"38[,\s]?000", msg)) or "38000" in msg or "38k" in lower,
        "invoice" in lower,
    ]
    return sum(1 for c in checks if c) >= 4


async def main() -> None:
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.", file=sys.stderr)
        sys.exit(1)

    out = await ai_spend_agent("Anthropic", 4200.0, ACME_COMPANY_ID)
    print(out)

    assert out.get("pillar") == "ai_spend", out
    assert out.get("spike_detected") is True, out
    assert out.get("requires_action") is True, out
    msg = str(out.get("message") or "")
    assert _message_covers_seed(msg), msg

    print("OK — AI spend agent matches seed expectations (Anthropic $4200).")


if __name__ == "__main__":
    asyncio.run(main())
