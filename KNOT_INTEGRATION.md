# Knot Integration

End-to-end integration of [Knot Transaction Link](https://docs.knotapi.com/) into Flux.

- **Supabase remains the source of truth.** Knot is upstream only.
- Existing rows, listeners, and agents keep working unchanged. A new `provider` column defaults to `'manual'`.
- Knot transactions are upserted into the existing `transactions` table; the existing Realtime listener routes them through the orchestrator and into iMessage alerts the same way manual rows do.
- Webhook-driven primary path; manual sync available from the UI.
- All sync runs and webhook events are persisted for replay/observability.

## Architecture summary

```
        Browser (Connect tab)                 Knot SDK / Knot servers
               │                                       │
       1. POST /knot/session                           │
               ▼                                       │
        FastAPI orchestrator   ◀── 5. POST /webhooks/knot ──┘
        ┌─────────────────────┐
        │ /knot/session       │   creates session_id
        │ /knot/sync          │   pulls /transactions/sync (cursor loop)
        │ /webhooks/knot      │   AUTHENTICATED, NEW_TRANSACTIONS_AVAILABLE,
        │                     │   UPDATED_TRANSACTIONS_AVAILABLE,
        │                     │   ACCOUNT_LOGIN_REQUIRED
        └─────────┬───────────┘
                  │ upsert (provider, external_id)
                  ▼
              Supabase
        ┌─────────────────────┐
        │ transactions        │ ◀── INSERT triggers existing Realtime
        │ knot_merchant_acct  │     listener → orchestrator → agents → iMessage
        │ knot_sync_cursors   │
        │ knot_webhook_events │
        │ knot_sync_log       │
        └─────────────────────┘
```

### What we extended in Supabase (migration `007_knot_integration.sql`)

- `transactions` gains: `provider` (default `manual`), `external_id`, `external_user_id`, `merchant_id`, `merchant_name`, `order_status`, `currency`, `occurred_at`, `order_url`, `payment_methods` (JSONB), `products` (JSONB), `shipping` (JSONB), `raw_payload` (JSONB).
- Idempotency: `UNIQUE INDEX (provider, external_id) WHERE external_id IS NOT NULL`.
- `companies.knot_external_user_id` (`company:<UUID>`) — back-filled.
- New tables: `knot_merchant_accounts`, `knot_sync_cursors`, `knot_webhook_events`, `knot_sync_log`.
- Realtime publication adds `knot_merchant_accounts` and `knot_sync_log`.

### Key files

| Layer | File | Role |
|---|---|---|
| Orchestrator | `orchestrator/integrations/knot/client.py` | HTTP client (Basic Auth, retries, dev simulator) |
| Orchestrator | `orchestrator/integrations/knot/normalize.py` | Knot txn → `transactions` row mapper |
| Orchestrator | `orchestrator/integrations/knot/ingest.py` | Cursor sync loop, upsert, sync log, account upsert |
| Orchestrator | `orchestrator/integrations/knot/router.py` | FastAPI endpoints + `/webhooks/knot` |
| Orchestrator | `orchestrator/integrations/knot/log.py` | Structured stdout logger |
| Orchestrator | `orchestrator/main.py` | Wires `knot_router`, logs env wiring at startup, CORS allowlist |
| DB | `flux/supabase/migrations/007_knot_integration.sql` | Schema additions |
| Frontend (Next.js) | `web/app/connect/page.tsx` + `ConnectClient.tsx` | Connect tab UI (App Router) |
| Frontend (Next.js) | `web/lib/knot.ts` | Typed client: orchestrator REST + Knot Web SDK loader |
| Frontend (Next.js) | `web/components/Navbar.tsx` + `Toast.tsx` | App shell |
| Frontend (Next.js) | `web/app/layout.tsx` | Root layout, CSS, ToastProvider |

> **Note on `/frontend/`** — the `/frontend/` Vite SPA in this repo is a legacy
> prototype dashboard. The Knot integration ships in the new Next.js app under
> `/web/`. The Vite app is left in place for reference but no Knot work depends
> on it.

## Setup

### 1. Apply the migration

```bash
cd /root/Vertex/flux
# whichever flow you normally use:
supabase db push                                 # Supabase CLI
# or psql against your remote DB:
psql "$SUPABASE_DB_URL" -f supabase/migrations/007_knot_integration.sql
```

The migration is **additive and idempotent** (`if not exists`, `if not exists` indexes, `do nothing` defaults). Safe to re-run.

### 2. Set env vars

**Backend** — copy `flux/.env.local.example` to `flux/.env.local` and fill in:

```bash
KNOT_CLIENT_ID=...                    # https://dashboard.knotapi.com/developers/keys
KNOT_SECRET=...
KNOT_ENVIRONMENT=development          # development | production
KNOT_PUBLIC_WEBHOOK_URL=https://YOUR_NGROK_HOST/webhooks/knot
KNOT_VERIFY_WEBHOOKS=1                # HMAC-verify Knot-Signature against KNOT_SECRET
FLUX_COMPANY_ID=00000001-0000-4000-8000-000000000001
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=...              # service role; backend only
# Optional CORS override, defaults to localhost:3000-3002
# FLUX_CORS_ORIGINS=https://app.example.com
```

**Frontend** — copy `web/.env.local.example` to `web/.env.local`:

```bash
NEXT_PUBLIC_ORCHESTRATOR_URL=http://localhost:8000
```

`run_orchestrator.sh` sources `flux/.env.local` (or `flux/.env`); the Next app reads `web/.env.local` directly.

### 3. Configure the Knot Dashboard webhook

Go to https://dashboard.knotapi.com/developers/webhooks and add `KNOT_PUBLIC_WEBHOOK_URL` for the **development** environment. For local dev, expose port 8000 via ngrok:

```bash
ngrok http 8000
# copy https://xxxx.ngrok-free.app -> KNOT_PUBLIC_WEBHOOK_URL=https://xxxx.ngrok-free.app/webhooks/knot
```

### 4. Run everything

Three terminals:

```bash
# Terminal 1 — orchestrator (logs Knot env, sessions, webhooks, sync pages)
cd /root/Vertex/orchestrator && ./run_orchestrator.sh

# Terminal 2 — iMessage bridge (existing)
cd /root/Vertex/imessage-bridge && npm run dev

# Terminal 3 — Next.js frontend
cd /root/Vertex/web && npm install && npm run dev   # http://localhost:3002/connect
```

## How to test locally

The fastest path that requires no real merchant credentials is the **development simulator** Knot exposes at `POST /development/accounts/link`. It generates ~205 sample transactions and emits the same webhooks a real link would.

### Path A — Simulator (no SDK required)

1. Open `http://localhost:3002/connect`.
2. Top-right pill shows **"Knot · development · connected"** when env vars are wired.
3. Click **"Simulate link (dev)"** on any merchant card (e.g. DoorDash #19).
4. Watch the orchestrator stdout for:
   - `env.check ...`
   - `api.dev_simulate_link external_user_id=... merchant_id=19`
   - `webhook.received event=AUTHENTICATED ...`
   - `webhook.received event=NEW_TRANSACTIONS_AVAILABLE ...`
   - `sync.start ...` → `sync.page page=1 fetched=...` → `sync.upsert page=1 inserted=... updated=0` (loops until `next_cursor=null`)
   - `sync.done pages=N inserted=N updated=0`
5. The Connect page **Recent sync runs** + **Recent webhook events** tables populate within ~5s.
6. Switch to the **Dashboard** tab — new transactions appear in spend totals.
7. Inside iMessage (if Photon bridge is up), the orchestrator's existing listener fires `route_transaction` for each new row → agents reason → `agent_alerts` → `send_to_founder`.

### Path B — Real merchant link via Web SDK

1. Click **"Connect via SDK"** on a merchant.
2. Browser asks orchestrator for a session_id (`POST /knot/session`) — orchestrator logs `session.create` and `api.create_session`.
3. The Knot modal opens and prompts the user for merchant credentials.
4. On success, Knot delivers `AUTHENTICATED` to `KNOT_PUBLIC_WEBHOOK_URL`, then shortly after delivers `NEW_TRANSACTIONS_AVAILABLE` — the orchestrator logs all of it and runs the sync loop.

### Manual sync

Click **"Sync now"** on any linked-account row, or:

```bash
curl -X POST http://localhost:8000/knot/sync \
  -H "content-type: application/json" \
  -d '{"merchant_id": 19, "trigger": "manual"}'
```

## Observability — where to look

| Where | What you see |
|---|---|
| Orchestrator stdout | `env.check`, `api.*`, `session.create`, `webhook.received`, `webhook.processing`, `sync.start/page/upsert/done`, `account.upsert`, `webhook.account_login_required`, errors |
| `GET /knot/health` | env var presence + live `list_merchants` ping |
| `GET /knot/sync/log?limit=25` | every sync run with pages/inserted/updated/duration/status |
| `GET /knot/webhook/events?limit=25` | every webhook with full payload + processing status |
| Connect tab → "Recent sync runs" / "Recent webhook events" | same data, polled every 5s |
| Supabase `transactions` table | new rows with `provider='knot'` and full Knot payload in `raw_payload` |

The frontend deliberately surfaces high-level UI state only. Detailed Knot activity (env, SDK session ids, login/logout, sync pages, webhook deliveries) is only visible in the **orchestrator backend logs** + Supabase tables — not in the browser console.

## Test plan

### Happy paths

- [ ] **Health**: `curl localhost:8000/knot/health` → `ok: true`, env shows credentials present.
- [ ] **Merchants**: `curl localhost:8000/knot/merchants` → array of merchants, includes `id: 19` (DoorDash).
- [ ] **Session**: `curl -X POST localhost:8000/knot/session` → `{ session: "...", external_user_id: "company:..." }`.
- [ ] **Simulator → Sync → Insert → Listener → Agent → Alert** (end-to-end):
  1. Simulate link DoorDash via UI.
  2. Within ~5s, orchestrator logs `webhook.received event=AUTHENTICATED`.
  3. Within ~10s, logs `webhook.received event=NEW_TRANSACTIONS_AVAILABLE` then `sync.start`/`sync.page`/`sync.done`.
  4. `select count(*) from transactions where provider='knot'` increments by ~205.
  5. Existing listener fires `route_transaction` per row; `agent_alerts` rows accumulate.
  6. `send_to_founder` calls Photon bridge for any rows where `requires_action`.

### Idempotency / duplicate prevention

- [ ] Re-run the same simulator call (same `external_user_id`, same merchant) → orchestrator logs same rows; `select count(*) from transactions where provider='knot'` does **not** double.
- [ ] Re-deliver the same webhook payload manually → second `knot_webhook_events` row written, but no new `transactions` rows; `sync_log` shows `inserted=0 updated=>0`.
- [ ] Manually trigger `POST /knot/sync` immediately after a webhook-driven sync → `sync_log` shows `inserted=0`.

### Re-sync behaviour (cursor)

- [ ] First simulator: `cursor_before=null`, `cursor_after=null` after final page; `pages_fetched ≥ 1`.
- [ ] Second simulator (same user, same merchant, with `new=true,updated=true`) → updates flow through `UPDATED_TRANSACTIONS_AVAILABLE` → `ingest_updated_transactions` → `inserted=0, updated=N` for the changed rows.

### Failure cases

- [ ] Wrong creds: orchestrator logs `health.api_error 401`; UI pill shows red "error".
- [ ] Webhook reaches us but `sync_transactions` raises 5xx → `knot_webhook_events.status='error'`, `knot_sync_log.status='error'` with `error` populated, account row marked `error` with `last_error`.
- [ ] `ACCOUNT_LOGIN_REQUIRED` webhook arrives → account row flips to `connection_status='disconnected'` and the UI shows it.

### Listener / alert anti-spam

- [ ] After ingestion, observe `agent_alerts` rows fire **once per new transaction**.
- [ ] Trigger updates → `transactions` rows are mutated (UPDATE), no new INSERT events fire, no new `agent_alerts` are created. Confirms we never re-spam the founder for the same transaction.

## Verification checklist

Run these in order; each should pass before the next.

1. `psql "$SUPABASE_DB_URL" -c "\\d transactions"` shows `provider`, `external_id`, `raw_payload`, …
2. `psql "$SUPABASE_DB_URL" -c "\\dt knot_*"` shows `knot_merchant_accounts`, `knot_sync_cursors`, `knot_webhook_events`, `knot_sync_log`.
3. Orchestrator boots and prints `[knot] env.check KNOT_ENVIRONMENT=development KNOT_CLIENT_ID_present=true ...`.
4. `curl localhost:8000/knot/health` returns `ok: true` and a non-empty `merchants` count.
5. Open `http://localhost:3000/#connect` — top-right shows green "Knot development · connected"; merchant grid renders.
6. Click **Simulate link (dev)** on DoorDash — toast: "Simulated link …"; orchestrator logs the chain `api.dev_simulate_link → webhook.received AUTHENTICATED → account.upsert → webhook.received NEW_TRANSACTIONS_AVAILABLE → sync.start → sync.page → sync.upsert → sync.done`.
7. `select count(*) from transactions where provider='knot'` returns ~205.
8. `select * from knot_sync_log order by started_at desc limit 1` shows `status='success'`, `inserted>0`, `pages_fetched>=1`.
9. `select * from knot_webhook_events order by received_at desc limit 5` shows all events `status='done'`.
10. Run the simulator again — `inserted=0` in the new `knot_sync_log` row (idempotency verified).
11. Reload Dashboard tab — KPI deltas reflect the new rows.

## Known limitations

- **Web SDK domain allowlisting**: Production Web SDK usage requires the domain to be allowlisted in https://dashboard.knotapi.com/developers/domains. Use Path A (simulator) for local dev unless you've allowlisted localhost.
- **Webhook signing**: Knot does not currently expose an HMAC signing scheme in their public docs at the time of writing; we accept all POSTs to `/webhooks/knot`. Lock this down with IP allowlisting / mTLS / a shared header in production.
- **Card-link**: Not implemented — Transaction Link gives the data Flux needs (SKU-level transactions). Card-link is product-gated and orthogonal to this integration.
- **Scheduled refresh**: Not added. The webhook-driven path covers refresh; if you need a periodic safety-net sweep, run the manual `POST /knot/sync` from cron with `trigger=scheduled`.
