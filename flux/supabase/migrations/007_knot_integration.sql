-- ============================================================
-- 007_knot_integration.sql — Knot upstream integration
--
-- Additive only. Existing rows keep working: provider defaults
-- to 'manual' so all current seed data and any future manual
-- inserts behave exactly as before.
--
-- New columns on transactions   ── Knot-specific metadata + raw payload
-- New tables                    ── linked merchant accounts, sync cursors,
--                                  webhook event audit, sync run log
-- Idempotency                   ── UNIQUE (provider, external_id)
-- Listener compatibility        ── still INSERT-driven; Knot inserts new
--                                  rows, updates only mutate the same row
-- ============================================================

-- ─── transactions: extend additively ─────────────────────────
alter table transactions add column if not exists provider          text not null default 'manual';
alter table transactions add column if not exists external_id       text;            -- Knot transaction id
alter table transactions add column if not exists external_user_id  text;            -- Knot external_user_id
alter table transactions add column if not exists merchant_id       integer;         -- Knot merchant id
alter table transactions add column if not exists merchant_name     text;            -- Knot merchant name
alter table transactions add column if not exists order_status      text;            -- ORDERED | BILLED | ...
alter table transactions add column if not exists currency          text;
alter table transactions add column if not exists occurred_at       timestamptz;     -- transaction.datetime
alter table transactions add column if not exists order_url         text;
alter table transactions add column if not exists payment_methods   jsonb;
alter table transactions add column if not exists products          jsonb;
alter table transactions add column if not exists shipping          jsonb;
alter table transactions add column if not exists raw_payload       jsonb;

-- Constrain provider values
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'transactions_provider_chk'
  ) then
    alter table transactions
      add constraint transactions_provider_chk
      check (provider in ('manual','knot','seed','import'));
  end if;
end $$;

-- Idempotency: a given (provider, external_id) can appear at most once.
-- Partial unique to allow many manual rows whose external_id is null.
create unique index if not exists transactions_provider_external_uidx
  on transactions(provider, external_id)
  where external_id is not null;

create index if not exists transactions_external_user_idx
  on transactions(external_user_id)
  where external_user_id is not null;

create index if not exists transactions_merchant_id_idx
  on transactions(merchant_id)
  where merchant_id is not null;

create index if not exists transactions_occurred_at_idx
  on transactions(company_id, occurred_at desc)
  where occurred_at is not null;

-- ─── companies: stable Knot external_user_id mapping ─────────
alter table companies add column if not exists knot_external_user_id text;

update companies
   set knot_external_user_id = 'company:' || id::text
 where knot_external_user_id is null;

create unique index if not exists companies_knot_external_user_uidx
  on companies(knot_external_user_id)
  where knot_external_user_id is not null;


-- ─── knot_merchant_accounts ──────────────────────────────────
-- One row per (company, merchant) the user has linked through Knot.
create table if not exists knot_merchant_accounts (
  id                 uuid default gen_random_uuid() primary key,
  company_id         uuid references companies(id) on delete cascade,
  external_user_id   text not null,
  merchant_id        integer not null,
  merchant_name      text,
  connection_status  text not null default 'connected',
    -- connected | disconnected | error
  last_session_id    text,
  last_authenticated_at timestamptz,
  last_synced_at     timestamptz,
  last_error         text,
  created_at         timestamptz default now(),
  updated_at         timestamptz default now(),
  unique (external_user_id, merchant_id)
);

create index if not exists knot_merchant_accounts_company_idx
  on knot_merchant_accounts(company_id, connection_status);


-- ─── knot_sync_cursors ───────────────────────────────────────
-- One opaque cursor per (external_user_id, merchant_id). Persisted
-- after each page so crash-recovery resumes correctly.
create table if not exists knot_sync_cursors (
  id                 uuid default gen_random_uuid() primary key,
  external_user_id   text not null,
  merchant_id        integer not null,
  cursor             text,
  updated_at         timestamptz default now(),
  unique (external_user_id, merchant_id)
);


-- ─── knot_webhook_events ─────────────────────────────────────
-- Audit + replay log of every Knot webhook we've received.
create table if not exists knot_webhook_events (
  id                 uuid default gen_random_uuid() primary key,
  event              text not null,
  external_user_id   text,
  merchant_id        integer,
  merchant_name      text,
  session_id         text,
  task_id            text,
  payload            jsonb not null,
  received_at        timestamptz default now(),
  processed_at       timestamptz,
  status             text default 'received',
    -- received | processing | done | error
  error              text
);

create index if not exists knot_webhook_events_received_idx
  on knot_webhook_events(received_at desc);
create index if not exists knot_webhook_events_event_idx
  on knot_webhook_events(event, received_at desc);


-- ─── knot_sync_log ───────────────────────────────────────────
-- One row per sync run (manual, webhook-driven, or scheduled).
create table if not exists knot_sync_log (
  id                 uuid default gen_random_uuid() primary key,
  company_id         uuid references companies(id) on delete cascade,
  external_user_id   text not null,
  merchant_id        integer not null,
  trigger            text not null,
    -- webhook | manual | scheduled | initial
  pages_fetched      integer default 0,
  inserted_count     integer default 0,
  updated_count      integer default 0,
  cursor_before      text,
  cursor_after       text,
  status             text default 'running',
    -- running | success | error
  error              text,
  started_at         timestamptz default now(),
  finished_at        timestamptz,
  duration_ms        integer
);

create index if not exists knot_sync_log_company_idx
  on knot_sync_log(company_id, started_at desc);


-- ─── Realtime publication ────────────────────────────────────
-- transactions is already in supabase_realtime; new Knot rows
-- will fire INSERT events through the existing listener with no
-- code change. UPDATEs (UPDATED_TRANSACTIONS_AVAILABLE) will not
-- re-trigger agents — exactly what we want to prevent dup alerts.
do $$
begin
  begin
    alter publication supabase_realtime add table knot_merchant_accounts;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table knot_sync_log;
  exception when duplicate_object then null;
  end;
end $$;
