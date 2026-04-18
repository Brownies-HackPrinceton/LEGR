from __future__ import annotations

import asyncio
import os
from typing import Any, Dict

from supabase import create_client

from orchestrator import route_transaction


async def _handle_insert(record: Dict[str, Any]) -> None:
    # route_transaction expects a subset of transaction fields; realtime record has extras.
    await route_transaction(record)  # type: ignore[arg-type]


async def main() -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in environment")

    supabase = create_client(url, key)

    # supabase-py realtime client uses an internal event loop; keep this process alive.
    loop = asyncio.get_running_loop()

    def on_insert(payload: Dict[str, Any]) -> None:
        record = (payload.get("data") or {}).get("record") or {}
        if not isinstance(record, dict) or not record:
            return
        # Schedule handling in the current event loop (do NOT call asyncio.run here).
        loop.create_task(_handle_insert(record))

    channel = supabase.channel("transactions")
    channel.on_postgres_changes(
        event="INSERT",
        schema="public",
        table="transactions",
        callback=on_insert,
    )
    channel.subscribe()

    print("Listening for transaction inserts...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

