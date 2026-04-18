# Flux — Supabase schema + typed client

This folder contains **only** the Supabase database layer and a small TypeScript client for the Flux Next.js frontend:

- `supabase/migrations/001_schema.sql` — tables, indexes, and Realtime publication entries
- `supabase/migrations/002_seed.sql` — deterministic demo data for **Acme Labs**
- `lib/database.types.ts` — `Database` types for `@supabase/supabase-js`
- `lib/supabase.ts` — shared typed `supabase` client
- `lib/flux.ts` — async read/write helpers + Realtime subscriptions

There is **no** Python backend, Edge Functions, or agent runtime in this package.

## Prerequisites

- A [Supabase](https://supabase.com/) project (cloud or local via the [Supabase CLI](https://supabase.com/docs/guides/cli))
- Node.js 18+ (for installing the client dependency)

## 1) Create or link a Supabase project

### Cloud

1. In the Supabase dashboard, create a new project and wait for the database to finish provisioning.
2. Open **Project Settings → API** and copy:
   - **Project URL** (`NEXT_PUBLIC_SUPABASE_URL`)
   - **anon public** key (`NEXT_PUBLIC_SUPABASE_ANON_KEY`)

### Local (CLI)

From this `flux/` directory:

```bash
supabase start
```

Use the printed API URL and anon key as your environment variables.

## 2) Apply migrations

Migrations are plain SQL and are applied in filename order.

### Option A — Supabase CLI (recommended)

```bash
cd flux
supabase link --project-ref <YOUR_PROJECT_REF>   # cloud only
supabase db push                                 # applies pending migrations
```

For a clean local database:

```bash
supabase db reset
```

### Option B — Dashboard SQL editor

Run the contents of:

1. `supabase/migrations/001_schema.sql`
2. `supabase/migrations/002_seed.sql`
3. `supabase/migrations/003_seed_saas_expansion.sql` (extra SaaS + transactions + alerts; skip only if you already ran it once)
4. `supabase/migrations/004_saas_sprawl_services.sql` (overlaps, renewals, plan optimization, feature waste, shadow IT, savings log)

in order in **SQL → New query**.

## 3) Configure environment variables

Copy `flux/.env.local.example` to your Next.js app as `.env.local` (or merge the variables into an existing env file):

```bash
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

These **must** be available wherever `lib/supabase.ts` is imported (Next.js inlines `NEXT_PUBLIC_*` at build time for client bundles).

## 4) Install the client dependency

From `flux/`:

```bash
npm install
```

In your Next.js app, either:

- add `@supabase/supabase-js` to the app’s own `package.json`, **or**
- reference this folder as a workspace package / copy `lib/*.ts` into the app’s `lib/` tree.

The imports in `lib/supabase.ts` and `lib/flux.ts` assume `@supabase/supabase-js` v2 is resolvable from the app.

## 5) Use the typed helpers

```typescript
import {
  getCompany,
  getPendingAlerts,
  getRecentTransactions,
  logCharge,
  subscribeToAlerts,
} from './lib/flux'

const COMPANY_ID = '00000001-0000-4000-8000-000000000001' // Acme Labs (seed)

const company = await getCompany(COMPANY_ID)
const alerts = await getPendingAlerts(COMPANY_ID)

const unsubscribe = subscribeToAlerts(COMPANY_ID, (alert) => {
  console.log('New alert:', alert.message)
})
```

### Deterministic demo IDs (from seed)

| Entity        | ID |
|---------------|----|
| Acme Labs     | `00000001-0000-4000-8000-000000000001` |
| Sarah J.      | `00000001-0000-4000-8000-000000000010` |
| Marcus K.     | `00000001-0000-4000-8000-000000000011` |
| Alex L.       | `00000001-0000-4000-8000-000000000012` |
| Tom R.        | `00000001-0000-4000-8000-000000000013` |
| Priya S.      | `00000001-0000-4000-8000-000000000014` |
| Jordan M.     | `00000001-0000-4000-8000-000000000015` |
| Casey W.      | `00000001-0000-4000-8000-000000000016` |
| Riley B.      | `00000001-0000-4000-8000-000000000017` |

## Realtime notes

`001_schema.sql` adds `transactions` and `agent_alerts` to the `supabase_realtime` publication so `subscribeToTransactions` / `subscribeToAlerts` receive `INSERT` events.

If you filter Realtime rows by `company_id` and do not see events, confirm **Database → Replication** settings for your project and that the tables are included in the Realtime publication (the migration does this for fresh databases).

## Typecheck this package

```bash
cd flux
npx tsc --noEmit -p tsconfig.json
```
