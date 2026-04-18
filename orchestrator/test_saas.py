"""
Run: cd orchestrator && python test_saas.py
Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY (flux/.env). DEDALUS_API_KEY optional.
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

from agents.saas import saas_agent

ACME_COMPANY_ID = "00000001-0000-4000-8000-000000000001"


def _cursor_message_checks(msg: str) -> bool:
    lower = msg.lower()
    checks = [
        "cursor" in lower,
        "renew" in lower or "renews" in lower,
        "seat" in lower,
        "dormant" in lower or "ghost" in lower,
    ]
    return sum(1 for c in checks if c) >= 3


async def main() -> None:
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.", file=sys.stderr)
        sys.exit(1)

    out = await saas_agent("Cursor", 1400.0, ACME_COMPANY_ID)
    print(out)

    assert out.get("pillar") == "saas_sprawl", out
    assert out.get("requires_action") is True, out

    msg = str(out.get("message") or "")
    assert _cursor_message_checks(msg), msg

    print("OK — SaaS agent matches seed expectations (Cursor $1400).")


if __name__ == "__main__":
    asyncio.run(main())

