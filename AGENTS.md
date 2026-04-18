# AGENTS.md — Agent Context for Flux

> This file is the primary context for any AI coding agent (Codex, Cursor, etc.) working on this repo. Read SPEC.md and BUILD_PLAN.md in addition to this file before making changes.

## Project in one sentence

Flux is an AI CFO for startups that finds waste in AI and SaaS spend by reasoning over transaction data (Knot) and work-surface signals (GitHub/Gmail/Calendar), then takes one-tap action via iMessage (Photon), all orchestrated by a Dedalus agent swarm.

## The three hackathon tracks we are targeting and the rule for each

1. **Best Business & Enterprise** → the product must obviously save a startup real money with a clear B2B pitch
2. **Best Use of Knot** → Knot TransactionLink must be load-bearing (production, not sandbox) and provide the primary data feed
3. **Best Use of Dedalus** → Dedalus must do genuine multi-agent reasoning, not one-shot prompting. Orchestrator routes, specialists reason.
4. **Exploring Hybrid Intelligence (Photon)** → iMessage is the ENTIRE founder-facing UI. No web dashboard for user interaction.

**Hard rule:** If you catch yourself building a web page for the founder to click through, stop and move that flow into iMessage.

## Core design principles (non-negotiable)

1. **The iMessage thread is the audit log.** Every agent decision must be visible there. No hidden state.
2. **One Knot feed, three pillars.** AI spend, SaaS sprawl, expense compliance all flow from the same transaction stream routed by the orchestrator.
3. **Reasoning > rules.** Don't regex-match merchant names to categorize. Use Dedalus with Codex Sonnet 4.5 for anything that has ambiguity. The orchestrator's job is to REASON about routing.
4. **Real numbers only.** All demo data comes from one team member's real accounts. No synthetic CSVs.
5. **Every action is gated by founder iMessage approval.** Agent drafts, founder approves with Y/N, agent executes. Never execute autonomously in V1.

## Model routing policy (we eat our own dog food)

Since the product IS about AI cost optimization, our own stack should demonstrate it:

| Task | Model | Why |
|---|---|---|
| Orchestrator routing decisions | Codex Haiku 4.5 | Fast, cheap, good at structured output |
| AI-Spend Agent reasoning | Codex Sonnet 4.5 | Needs to actually reason about prompt patterns |
| SaaS Discovery (invoice parsing) | Gemini 2.5 Flash | Cheap OCR + structured extraction |
| Usage Signals (seat inference) | Codex Haiku 4.5 | Simple heuristics + light reasoning |
| Negotiation Agent (email drafting) | Codex Sonnet 4.5 | Tone matters, reasoning about BATNA |
| Compliance Agent | Codex Haiku 4.5 | Policy checking is near-deterministic |

## Things NOT to build (we have 24 hours)

- Multi-tenant auth — hardcode one demo company
- A web-based user interface for approving things — approval is iMessage Y/N
- Admin UI for policies — policy is a JSON file we hand-edit
- Real vendor negotiation replies — V1 is send-only
- Real middleware deployment — V1 shows the diff, says "deploys to your proxy"
- Tax features — not in scope, roadmap slide only
- QuickBooks integration — roadmap slide
- Employee mobile app — employees use native iMessage
- Slack/Teams/Discord integration — iMessage only

## Tech stack (locked)

- **Backend:** Python 3.11, FastAPI, SQLAlchemy (async), asyncpg
- **DB:** Postgres (local Docker), one schema, no migrations framework — raw SQL init
- **Agents:** Dedalus Labs SDK (Python)
- **LLMs:** Anthropic SDK (Codex), Google SDK (Gemini)
- **iMessage bridge:** Node.js + `@photon-ai/imessage-kit` (separate process)
- **Transactions:** Knot TransactionLink (production keys)
- **Email:** Gmail API (OAuth, single account)
- **Calendar:** Google Calendar API
- **Code signals:** GitHub REST API (PAT)
- **Demo dashboard:** Next.js + Tailwind + shadcn/ui (optional, low priority)
- **Hosting:** localhost + ngrok (no deployment — runs off demo laptop)

## File conventions

- All Python uses async/await where possible (FastAPI is async, DB is async)
- Pydantic for all API schemas
- One agent = one file under `backend/app/agents/`
- Integration clients one per file under `backend/app/integrations/`
- Long-running work goes through background tasks, not inline in handlers
- All LLM calls go through `backend/app/integrations/dedalus_client.py` — never call Anthropic/Gemini SDKs directly from agent code (this centralizes logging + usage tracking, which is itself demo material)

## Secret management

- All secrets in `.env` (see SPEC.md §10)
- NEVER commit `.env`
- The `.env.example` file must have placeholders for every env var the code reads

## Database schema

See SPEC.md §5 for the full DDL. Do not add new tables without updating SPEC.md first. The schema is intentionally minimal.

## API contract

See SPEC.md §8 for the endpoint list. When adding a new endpoint:
1. Update SPEC.md §8
2. Add Pydantic request/response models in `models.py`
3. Add the router in `backend/app/routers/`
4. Wire into `main.py`

## Agent protocol (how agents talk to each other)

Every agent returns a structured dict:

```python
{
    "agent": "ai_spend" | "saas_discovery" | ...,
    "findings": [
        {
            "summary": "<1 sentence human-readable>",
            "reasoning": "<full chain of thought>",
            "estimated_savings_cents": int,
            "confidence": float,  # 0 to 1
            "proposed_action": {
                "kind": "cancel_saas" | "deploy_routing" | ...,
                "payload": {...}
            }
        }
    ]
}
```

The orchestrator collects findings across agents, deduplicates, ranks by savings × confidence, and picks the top 3 for the daily digest.

## iMessage sender contract

Python code calls the Node bridge via HTTP:

```python
# backend/app/services/imessage_sender.py
async def send_imessage(to: str, body: str, action_id: str | None = None) -> None:
    # POST to Node bridge at IMESSAGE_BRIDGE_URL/send
    ...
```

The Node bridge stores the outgoing `action_id` so when a reply comes in, it can correlate back.

## Incoming iMessage handling

Node bridge POSTs to FastAPI `/webhooks/imessage`:

```json
{
  "from_phone": "+1...",
  "body": "Y",
  "received_at": "2026-04-18T..."
}
```

FastAPI looks up the most recent pending action for that phone number, interprets the body (Y/N/list/why/other), updates action status, and either executes the action or responds with more context.

## Demo-day priorities (if something is broken at T+20h)

1. **Working Knot → iMessage pipe** is non-negotiable. Protect at all costs.
2. **One working pillar end-to-end** (AI-Spend) beats three half-working pillars.
3. **Real reasoning trace visible** beats pretty UI.
4. **The projection dashboard is disposable.** If it breaks, drop it.

## When the agent is unsure what to do

1. Re-read SPEC.md for the intent
2. Check BUILD_PLAN.md for which phase we're in
3. Ask: "does this help the 3-minute demo?" If no, skip it.
4. Prefer small, working, ugly code over elegant incomplete code. 24 hours.

## What "done" looks like

A founder can:
1. Swipe a card → get an iMessage within 30s with context and next action
2. Upload an AI usage CSV → get a savings recommendation with reasoning
3. Receive a SaaS sprawl alert with evidence from their actual GitHub/Calendar
4. Tap Y on any alert → see the action execute (email sent, config shown, etc.)
5. See a running "total savings found" number on a projection screen

That's the product. Everything else is 2027.
