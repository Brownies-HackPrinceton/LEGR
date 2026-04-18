import asyncio
import os

from dedalus_labs import AsyncDedalus, DedalusRunner


async def main() -> None:
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEDALUS_API_KEY in environment")

    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)

    response = await runner.run(
        input="Hello, what can you do?",
        model="anthropic/claude-opus-4-5",
        max_tokens=256,
    )
    print(response.final_output)


if __name__ == "__main__":
    asyncio.run(main())
