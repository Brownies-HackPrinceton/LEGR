# Flux — Project Spec

> **Rocket Money on steroids for startup founders.** An AI CFO that lives in iMessage, finds waste in AI/SaaS spend by reasoning over transaction + usage data, and takes action with one-tap approval.

**Hackathon:** HackPrinceton Fall 2025 — Business & Enterprise track
**Target prizes:** Best Business & Enterprise + Best Use of Knot + Best Use of Dedalus + Exploring Hybrid Intelligence (Photon)
**Time budget:** 24 hours

---

## 1. What we are building

A system that:
1. Ingests a startup's corporate card transactions via **Knot TransactionLink** (production, not sandbox)
2. Ingests AI API usage (Anthropic/OpenAI exports) and work-surface signals (Gmail, Calendar, GitHub)
3. Runs a **Dedalus agent swarm** that reasons about waste across three pillars:
   - **AI spend optimization** — wrong-model calls, forgotten batch jobs
   - **SaaS sprawl (Shadow)** — ghost seats, zombie subscriptions, bad renewal terms
   - **Expense compliance** — sketchy card swipes, policy violations
4. Surfaces findings and actions to the founder via **Photon iMessage** — one thread, tap-to-approve
5. Executes approvals (send cancellation emails, deploy routing middleware, log expenses) via MCP tools

**Non-goals for this build:** tax filing, a web dashboard, a mobile app, Slack integration, employee portal, billing, auth beyond a single demo user.

---

## 2. Why each sponsor technology is load-bearing

| Tech | Role | Why load-bearing |
|---|---|---|
| **Knot TransactionLink** | Transaction + merchant + subscription data source | No Knot = no spend data = no product. Must use prod. |
| **Dedalus** | Multi-agent orchestration + routing + reasoning | One agent can't do this. The orchestrator reasons about each transaction to route to specialists. Non-trivial multi-step reasoning. |
| **Photon iMessage Kit** | Entire founder-facing UI | Zero web UI. The iMessage thread IS the product and the audit log. |
| **Gemini 2.5 Flash** | Receipt/invoice OCR + document understanding | Gmail invoices need to be parsed to structured data. |
| **Snowflake** (optional but recommended) | Unified time-series store for transactions + usage | Time-series analysis is what enables "week-over-week" reasoning. Falls back to Postgres if time-constrained. |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       DATA INGESTION LAYER                       │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   Knot       │   Gmail      │   Calendar   │   Direct APIs      │
│ TransactionLink│  (via API)  │  (via API)   │ (Anthropic/OpenAI  │
│              │              │              │  usage exports)    │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬─────────────┘
       │              │              │              │
       └──────────────┴──────┬───────┴──────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   POSTGRES (or Snowflake)                        │
│   tables: transactions, subscriptions, usage_events, actions     │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              DEDALUS ORCHESTRATOR AGENT                          │
│   inputs: new event (txn / usage spike / scheduled digest)       │
│   outputs: routed sub-task → specialist agent                    │
└──┬────────────┬─────────────┬─────────────┬────────────┬────────┘
   ▼            ▼             ▼             ▼            ▼
┌──────┐   ┌─────────┐   ┌──────────┐  ┌──────────┐ ┌──────────┐
│ AI-  │   │ SaaS    │   │ Usage    │  │Negotiate │ │Compliance│
│Spend │   │Discovery│   │ Signals  │  │ Agent    │ │ Agent    │
│Agent │   │ Agent   │   │ Agent    │  │          │ │          │
└──────┘   └─────────┘   └──────────┘  └──────────┘ └──────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│        FastAPI BACKEND  (orchestration + state machine)          │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│          PHOTON iMESSAGE KIT (Node.js bridge)                    │
│   Founder thread • action approval • daily/weekly digests        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Tech stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.11 + FastAPI** | Dedalus SDK is Python-only. FastAPI is async + fast to build. |
| iMessage bridge | **Node.js + `@photon-ai/imessage-kit`** | Photon SDK is Node. Thin bridge that calls FastAPI. |
| Database | **Postgres** (local Docker) | Simpler than Snowflake for 24h. Add Snowflake if time. |
| Frontend (optional demo dashboard) | **Next.js + Tailwind + shadcn/ui** | Only for the "live cost ticking down" projection during demo. |
| Agent orchestration | **Dedalus Labs SDK** | Track requirement. |
| LLMs | **Claude Sonnet 4.5** (reasoning), **Gemini 2.5 Flash** (OCR), **Haiku** (cheap classification) | Mixed-model routing IS the product thesis |
| Transaction data | **Knot TransactionLink (production)** | Track requirement. |
| Email actions | **Gmail API** (OAuth) | For sending cancellation emails |
| Calendar signals | **Google Calendar API** | For usage inference |
| GitHub signals | **GitHub REST API (PAT)** | For Cursor seat usage inference |
| Deployment | **localhost + ngrok tunnel** | No time to deploy. Demo from laptop. |

---

## 5. Data model

```sql
-- core tables (Postgres)

CREATE TABLE companies (
  id UUID PRIMARY KEY,
  name TEXT,
  founder_phone TEXT,  -- for iMessage
  policy_json JSONB     -- parsed policy rules
);

CREATE TABLE employees (
  id UUID PRIMARY KEY,
  company_id UUID REFERENCES companies(id),
  name TEXT,
  email TEXT,
  phone TEXT,
  github_username TEXT
);

CREATE TABLE transactions (
  id UUID PRIMARY KEY,
  company_id UUID REFERENCES companies(id),
  employee_id UUID REFERENCES employees(id),
  knot_transaction_id TEXT UNIQUE,
  merchant TEXT,
  amount_cents INTEGER,
  category TEXT,        -- 'ai_api' | 'saas' | 'expense' | 'unknown'
  occurred_at TIMESTAMPTZ,
  raw_json JSONB,       -- full Knot payload
  status TEXT,          -- 'new' | 'classified' | 'flagged' | 'approved' | 'rejected'
  confidence FLOAT,
  agent_reasoning TEXT
);

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY,
  company_id UUID REFERENCES companies(id),
  vendor TEXT,          -- 'Cursor', 'Notion', 'Figma'
  seats_paid INTEGER,
  seats_active INTEGER, -- computed by Usage Signals Agent
  monthly_cost_cents INTEGER,
  renewal_date DATE,
  per_seat_usage JSONB  -- {employee_id: confidence_0_to_1}
);

CREATE TABLE ai_usage_events (
  id UUID PRIMARY KEY,
  company_id UUID REFERENCES companies(id),
  provider TEXT,        -- 'openai' | 'anthropic'
  model TEXT,           -- 'gpt-4', 'claude-opus-4', etc.
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_cents INTEGER,
  occurred_at TIMESTAMPTZ,
  prompt_pattern_hash TEXT,  -- for clustering similar calls
  recommended_model TEXT,    -- set by AI-Spend Agent
  potential_savings_cents INTEGER
);

CREATE TABLE actions (
  id UUID PRIMARY KEY,
  company_id UUID REFERENCES companies(id),
  kind TEXT,            -- 'cancel_saas' | 'deploy_routing' | 'approve_expense' | 'negotiate_renewal'
  target_ref TEXT,      -- subscription_id, transaction_id, etc.
  payload JSONB,        -- draft email, middleware config, etc.
  status TEXT,          -- 'pending' | 'approved' | 'rejected' | 'executed'
  created_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ,
  executed_at TIMESTAMPTZ,
  imessage_thread_id TEXT
);
```

---

## 6. The Dedalus agent swarm

### 6.1 Orchestrator Agent
**Job:** Receive every new event (Knot webhook, scheduled digest, usage spike) and route to the right specialist.

**System prompt (pseudocode):**
```
You are the Flux orchestrator. You receive events and decide
which specialist agent should handle them.

Event types:
- transaction.new → classify merchant, route to AI-Spend | SaaS | Compliance
- usage.spike → route to AI-Spend
- digest.daily → call all agents, compile summary
- action.reply → route to Negotiate if email thread, else handle inline

For each event, output JSON:
{
  "route_to": "ai_spend" | "saas_discovery" | "usage_signals" | "negotiate" | "compliance",
  "reason": "<1 sentence>",
  "priority": "low" | "medium" | "high"
}
```

### 6.2 AI-Spend Agent (the hero)
**Job:** Analyze AI API usage, find wrong-model calls, calculate savings, draft routing recommendations.

**Inputs:** `ai_usage_events` rows for last N days
**Outputs:** action of kind `deploy_routing` with payload describing which prompt patterns to re-route to cheaper models

**Reasoning task:** Given a prompt pattern (input/output token distribution, task type inferred from prompts), decide: could Haiku or Gemini Flash handle this at ≥90% parity? This is where **Claude Sonnet 4.5 or k2 Think v2** reasoning is load-bearing.

### 6.3 SaaS Discovery Agent
**Job:** Parse Gmail invoices + Knot subscription data → identify every SaaS tool the company pays for.

**Inputs:** Gmail search for invoice-like emails, Knot recurring subscription detection
**Outputs:** upserts to `subscriptions` table

### 6.4 Usage Signals Agent (the secret weapon)
**Job:** For each subscription, compute per-seat usage confidence.

**Inputs:**
- GitHub commits per employee (for Cursor/Copilot/dev tools)
- Calendar events per employee (for design tools, meeting tools)
- Gmail notification frequency per employee per vendor

**Reasoning:** "Is there evidence in employee X's work surface that they did the kind of work this tool exists for?" Not "did they log in."

**Outputs:** updates `subscriptions.per_seat_usage` and `seats_active`

### 6.5 Negotiate Agent
**Job:** Draft and send cancellation or renewal-negotiation emails.

**Inputs:** action of kind `cancel_saas` or `negotiate_renewal`
**Outputs:** email draft → after founder approval via iMessage, actually sends via Gmail API

### 6.6 Compliance Agent
**Job:** For expense-category transactions, score against company policy. If confidence high, auto-approve. If low, ping employee for context. If still unclear, escalate to founder.

**Inputs:** `transactions` row with category='expense', `companies.policy_json`
**Outputs:** action of kind `approve_expense` with confidence + reasoning

---

## 7. Photon iMessage UX

### 7.1 Founder thread message types

**Real-time alert (high-priority event):**
```
🚨 OpenAI bill hit $4,200 this week. Up 340% from last week.

Traced: batch job running GPT-4 on invoice classification.
38K calls. Haiku would handle at 94% parity.

Est. savings: $2,840/mo.

Deploy routing middleware? Reply Y or N.
```

**Daily digest (8am cron):**
```
📊 Yesterday's spend review

New: OpenAI $340, Anthropic $500, Notion seat added
Flagged: Midjourney $200/mo (21 days unused)

3 actions waiting. Reply "list" to see them.
```

**SaaS renewal heads-up (7 days before):**
```
⏰ Cursor renewal in 6 days — $1,400

Usage audit: 14 seats, 8 active, 6 dormant 30+ days
Recommend: downgrade to 8 seats + ask for 15% off

Send negotiation email? Reply Y or N.
```

**Expense FYI (low-priority passive):**
```
FYI: Sarah swiped $89 at Capital Grille.
Confirmed client dinner (Acme/Mike Chen).
Policy ✓, auto-approved. No action needed.
```

### 7.2 Employee thread (rarely triggered)

```
Agent: Saw $340 Notion charge on your card.
       New workspace or personal? Quick note helps.

Sarah: Team workspace for the design group.

Agent: Got it, thanks ✅
```

### 7.3 Intent parsing on reply

Founder replies are parsed with a small classifier:
- `Y` / `yes` / `approve` / `go` → execute pending action
- `N` / `no` / `reject` / `skip` → mark action rejected
- `list` / `show` / `what` → enumerate pending actions
- `why` / `how` → return agent reasoning trace
- anything else → pass through to Dedalus for natural-language handling

---

## 8. API endpoints (FastAPI)

```
POST /webhooks/knot              # Knot transaction webhook
POST /webhooks/imessage          # Photon → FastAPI bridge (incoming text)
POST /ingest/ai-usage            # upload Anthropic/OpenAI usage CSV
POST /ingest/gmail               # trigger Gmail sync (invoice scan)
POST /ingest/github              # trigger GitHub activity pull
POST /ingest/calendar            # trigger Calendar activity pull

GET  /agents/digest/daily        # run the daily digest agent (cron)
GET  /agents/run-analysis        # full re-analysis (for demo)

POST /actions/{id}/approve       # founder approved action
POST /actions/{id}/reject        # founder rejected action
POST /actions/{id}/execute       # trigger execution (send email etc.)

GET  /dashboard/live-numbers     # for demo projection: total spend, savings
```

---

## 9. Repo layout

```
flux/
├── backend/                    # FastAPI (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── db.py               # SQLAlchemy / asyncpg
│   │   ├── models.py           # Pydantic + SQLAlchemy models
│   │   ├── routers/
│   │   │   ├── webhooks.py
│   │   │   ├── ingest.py
│   │   │   ├── agents.py
│   │   │   └── actions.py
│   │   ├── agents/
│   │   │   ├── orchestrator.py
│   │   │   ├── ai_spend.py
│   │   │   ├── saas_discovery.py
│   │   │   ├── usage_signals.py
│   │   │   ├── negotiate.py
│   │   │   └── compliance.py
│   │   ├── integrations/
│   │   │   ├── knot.py
│   │   │   ├── gmail.py
│   │   │   ├── calendar.py
│   │   │   ├── github.py
│   │   │   └── dedalus_client.py
│   │   └── services/
│   │       ├── imessage_sender.py   # calls Node bridge
│   │       └── policy_parser.py
│   └── requirements.txt
│
├── imessage-bridge/            # Node.js (Photon SDK)
│   ├── index.js                # watches iMessage, forwards to FastAPI
│   ├── sender.js               # receives from FastAPI, sends iMessage
│   └── package.json
│
├── frontend/                   # Next.js demo dashboard (optional)
│   ├── app/
│   │   └── live/page.tsx       # "total savings ticking up" screen
│   └── package.json
│
├── scripts/
│   ├── seed_demo_data.py       # loads the canned demo transactions + usage
│   └── run_demo.py             # scripted demo runner
│
├── .env.example
├── docker-compose.yml          # postgres
└── README.md
```

---

## 10. Environment variables

```bash
# .env
DATABASE_URL=postgresql://flux:flux@localhost:5432/flux

# Dedalus
DEDALUS_API_KEY=...

# LLMs
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...           # Gemini

# Knot (PRODUCTION keys, not sandbox)
KNOT_CLIENT_ID=...
KNOT_SECRET=...
KNOT_ENVIRONMENT=production

# Photon
PHOTON_API_KEY=...
FOUNDER_PHONE=+1...
EMPLOYEE_PHONES={"sarah":"+1..."}

# Google APIs (OAuth)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...

# GitHub
GITHUB_PAT=...

# FastAPI ↔ Node bridge
IMESSAGE_BRIDGE_URL=http://localhost:3001
```

---

## 11. Demo data seeding

The demo must feel real. Pre-seed the DB with:

1. **10–15 real Knot transactions** from a team member's actual corporate/personal card (OpenAI, Anthropic, Vercel, Cursor, Notion, Figma, 2–3 restaurants, 1 Uber, 1 Amazon)
2. **Real AI usage export** from one team member's Anthropic console (last 30 days, downloadable as CSV)
3. **Real GitHub commits** pulled from the team's repo history
4. **Mock Gmail invoices** (pre-written, loaded into a synthetic mailbox OR read from actual Gmail if time permits)
5. **Synthetic employees** — Sarah (designer, uses Figma/Notion, no GitHub), Mike (dev, heavy GitHub/Cursor), Emma (PM, uses Linear/Notion)
6. **Pre-computed "ghost seats"** — Cursor paid for 14, Usage Signals shows only 8 active

---

## 12. Cut list (things we are NOT building)

- ❌ Auth beyond a hardcoded demo company
- ❌ Multi-tenant anything
- ❌ Web dashboard for management (only a projection screen for demo)
- ❌ Slack / Teams / Discord integration
- ❌ Tax filing or deduction tagging (roadmap slide only)
- ❌ Mobile app
- ❌ Settings/admin UI for policies (policy is a JSON file we hand-edit)
- ❌ Bookkeeping integration (QuickBooks) — roadmap slide
- ❌ Real negotiation (multi-turn email reply handling) — we demo send-only, say "v2 handles replies"
- ❌ Real middleware deployment — we show the diff / config file, say "deploys to your OpenRouter proxy"

---

## 13. Success criteria for the 3-minute demo

By judging time, we must be able to show:

1. ✅ A real card swipe → iMessage notification within 30 seconds (proves Knot + Photon end-to-end)
2. ✅ An AI spend alert with specific dollar savings and a reasoning trace from Dedalus (proves the hero pillar)
3. ✅ A SaaS ghost seat identified with evidence from GitHub/Calendar (proves Shadow)
4. ✅ An email actually flying out via Gmail MCP when founder taps Y (proves action, not just insight)
5. ✅ An employee clarifying-question loop running inline (proves platform, not feature)
6. ✅ A "total savings" number on a projection screen that ticks up as actions are approved (emotional payoff)
