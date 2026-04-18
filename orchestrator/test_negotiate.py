"""
Run: cd orchestrator && python test_negotiate.py
Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY. DEDALUS_API_KEY optional.

Note: If Dedalus is out of credits, the agent falls back to a deterministic email.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / "flux" / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from agents.negotiate import negotiate_agent

ACME_COMPANY_ID = "00000001-0000-4000-8000-000000000001"


async def main() -> None:
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.", file=sys.stderr)
        sys.exit(1)

    out = await negotiate_agent("Cursor", 1400.0, 15.0, ACME_COMPANY_ID)
    print(out)

    assert out.get("vendor") == "Cursor", out
    email = str(out.get("email_draft") or "")
    assert "Cursor" in email, email
    assert "discount" in email.lower(), email
    assert len(email) > 80, email

    print("OK — negotiate agent returned a draft email.")


if __name__ == "__main__":
    asyncio.run(main())

