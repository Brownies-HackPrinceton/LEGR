# LEGR

> 🏆 **Winner — Best Business & Enterprise Track**
> 🏆 **Winner — Best Use of Eragon**
> *HackPrinceton Spring 2026*

**Rocket Money on steroids for startups: a fleet of autonomous finance agents, long-running on Dedalus, conversational through Photon.**

LEGR handles the boring, expensive work of running a startup's finances — finding wasted AI spend, killing zombie SaaS subs, and negotiating renewals autonomously — all from inside your iMessage.

---
## What it does

🤖 **AI Spend Optimization** — catches wrong-model routing (Opus calls that should've been Haiku), idle credits, forgotten batch jobs.

📦 **SaaS Sprawl Killer** — finds ghost seats and zombie subs, then *negotiates renewals autonomously* instead of just flagging them.

💳 **Expense Compliance** — scores every card swipe against policy. Silent when clean, loud when off.

Founder taps `Y` once. LEGR handles 40+ hours of back-and-forth. One message when it's done: *"Closed. $4,140/yr saved."*

---

## Architecture

One thesis: **short-lived agents for stateless work, long-running Dedalus Machines for processes that outlive a single request.**

```
 INGESTION (Knot, Gmail MCP, Calendar MCP, Vendor APIs)
                      │
                      ▼
           SUPABASE (Postgres + Realtime)
                      │
                      ▼
        DEDALUS ORCHESTRATOR (stateless router)
         │         │         │         │
     await     await     await     spawn
         │         │         │         │
         ▼         ▼         ▼         ▼
      AI-Spend   SaaS    Compliance   DEDALUS MACHINE
       <5s       <5s       <1s         Negotiation Agent
                                       uptime: days/weeks
                                              │
                                              ▼
                                     PERSISTENT VOLUME
                                      /data/negotiations/
                                      /data/logs/
                                      /data/receipts/
                                              │
                                              ▼
                                     MACHINE LOOP
                                      loop · state · inbox
                                      reasoner · outbox
                      │
                      ▼
       PHOTON iMESSAGE  +  NEXT.JS DASHBOARD
       tiered: silent · FYI · decision-needed
```

**The Negotiation Machine** runs on a real VM with state on a persistent volume. Each deal has its own `{id}.json` state file tracking thread, round, and leverage used. Loop every 5 min: IMAP poll → Claude classifies reply → draft counter → SMTP send → atomic state write → sleep. Survives `kill -9` mid-negotiation.

---

## Stack

| Layer | Tech |
|---|---|
| Agent runtime | **Dedalus Machines** |
| Reasoning | **Dedalus + Claude Sonnet 4** |
| Interface | **Photon** (iMessage) + Next.js dashboard |
| Data | Supabase (Postgres + Realtime) |
| Ingestion | Knot TransactionLink, Gmail MCP, Calendar MCP |
| Email | IMAP inbound + Resend outbound |
| Webhooks | FastAPI |

---

## Repo structure

```
legr/
├── orchestrator.py        # stateless router: await vs spawn
├── agents/
│   ├── ai_spend.py        # short-lived
│   ├── saas.py            # short-lived
│   └── compliance.py      # short-lived
├── machines/
│   └── negotiation/       # long-running Dedalus Machine
│       ├── loop.py
│       ├── state.py       # atomic JSON writes
│       ├── inbox.py       # IMAP poll
│       ├── reasoner.py    # Claude reply classifier + drafter
│       └── outbox.py      # SMTP send via Resend
├── main.py                # FastAPI webhook entry
├── listener.py            # Supabase Realtime → orchestrator
└── dashboard/             # Next.js + Supabase Realtime
```

---

## Getting started

```bash
# Clone and install
git clone https://github.com/YOUR_USERNAME/legr
cd legr
pip install -r requirements.txt

# Environment
cp .env.example .env
# Set: SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY,
#      DEDALUS_API_KEY, PHOTON_API_KEY, RESEND_API_KEY, IMAP_*

# Run webhook server
python main.py

# Run Supabase Realtime listener (separate terminal)
python listener.py

# Run dashboard
cd dashboard && npm install && npm run dev
```

---

## Demo

1. Founder receives Photon alert: *"Cursor renewal in 7 days. Negotiate for 25% off? Y/N"*
2. Founder replies `Y`
3. Orchestrator spawns a Negotiation Machine
4. Machine drafts round 1, sends via Resend, monitors IMAP
5. Vendor replies with 15% → Claude classifies as `counter` → Machine drafts counter using past won deals as leverage → sends round 2
6. 2 days later, vendor accepts at 22%
7. Machine logs win, moves state to `/data/negotiations/closed/`, posts to Photon: *"Closed at 22% off + 4 seats removed. $4,140/yr saved."*

**The `kill -9` demo:** kill the Machine mid-negotiation, boot it, watch it read state and resume exactly where it left off.

---

## Built with

[Dedalus Machines](https://dedaluslabs.ai) · [Claude](https://anthropic.com) · [Photon](https://photon.im) · [Supabase](https://supabase.com) · [Knot](https://knotapi.com)
