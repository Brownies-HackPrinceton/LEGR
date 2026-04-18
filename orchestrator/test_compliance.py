"""
Run from repo: cd orchestrator && python test_compliance.py
Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY in env (see flux/.env or export).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load flux/.env if present (service key + URL live there in this repo layout)
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / "flux" / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from agents.compliance import compliance_agent

# Deterministic seed UUIDs (Acme Labs) — see flux/supabase/migrations/002_seed.sql
SARAH_ID = "00000001-0000-4000-8000-000000000010"
TOM_ID = "00000001-0000-4000-8000-000000000013"


async def main() -> None:
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.", file=sys.stderr)
        sys.exit(1)

    r1 = await compliance_agent(
        "Capital Grille",
        89.0,
        SARAH_ID,
        "Client dinner, Acme/Mike Chen",
    )
    print("Sarah / Capital Grille:", r1)
    assert r1["approved"] is True, r1

    r2 = await compliance_agent(
        "Nobu",
        680.0,
        TOM_ID,
        "Client entertainment",
    )
    print("Tom / Nobu:", r2)
    assert r2["approved"] is False, r2
    assert any("cap" in f.lower() for f in r2["flags"]), r2

    print("OK — compliance agent matches seed expectations.")


if __name__ == "__main__":
    asyncio.run(main())
