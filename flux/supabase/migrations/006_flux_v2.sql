-- ============================================================
-- 006_flux_v2.sql — Flux v2 schema additions
-- New: policies, policy_actions, negotiation_threads,
--      employee_threads, restraint_log, query_cache
--      employee.phone column, flux_query RPC
-- ============================================================

-- Add phone to employees for per-employee iMessage threads
alter table employees add column if not exists phone text;

-- Update demo employees with phone numbers
update employees set phone = '+16473306464' where name = 'Alice Johnson';
update employees set phone = '+14155552222' where name = 'Bob Smith';
update employees set phone = '+14155553333' where name = 'Carol Davis';
update employees set phone = '+14155554444' where name = 'David Lee';
update employees set phone = '+14155555555' where name = 'Emma Wilson';
update employees set phone = '+14155556666' where name = 'Frank Chen';
update employees set phone = '+14155557777' where name = 'Grace Kim';
update employees set phone = '+14155558888' where name = 'Henry Park';

-- ─── Policies ────────────────────────────────────────────────
create table if not exists policies (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  type text not null,
  -- types: auto_cancel | auto_accept_discount | auto_approve_expense
  --        production_infra | merchant_categorization
  enabled boolean default true,
  threshold_amount numeric,       -- dollar cap for the rule
  threshold_days integer,         -- inactivity window for auto_cancel
  threshold_discount_pct numeric, -- minimum % for auto_accept_discount
  production_infra_list text[] default '{}',
  description text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ─── Policy action audit log ──────────────────────────────────
create table if not exists policy_actions (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  policy_id uuid references policies(id) on delete set null,
  transaction_id uuid references transactions(id) on delete set null,
  action_type text not null,
  entity_name text,
  amount numeric,
  rationale text,
  executed_at timestamptz default now(),
  undo_available boolean default true,
  undone_at timestamptz
);

-- ─── Negotiation state machine ───────────────────────────────
create table if not exists negotiation_threads (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  vendor text not null,
  state text not null default 'pending',
  -- states: pending | draft_sent | waiting_reply | counter_received
  --         counter_sent | closed_won | closed_lost | stalled
  original_price numeric,
  target_discount_pct numeric,
  current_offer_pct numeric,
  policy_floor_pct numeric default 5.0,
  email_thread_id text,
  draft_email text,
  latest_vendor_reply text,
  turn_count integer default 0,
  outcome_notes text,
  started_at timestamptz default now(),
  updated_at timestamptz default now(),
  closed_at timestamptz,
  next_action_at timestamptz
);

-- ─── Restraint filter log ─────────────────────────────────────
create table if not exists restraint_log (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  alert_id uuid references agent_alerts(id) on delete set null,
  tier text not null, -- urgent | decision_needed | informational
  reason text,
  sent boolean default false,
  sent_at timestamptz,
  bundled_in_digest_at timestamptz,
  created_at timestamptz default now()
);

-- ─── Employee iMessage threads ────────────────────────────────
create table if not exists employee_threads (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  employee_id uuid references employees(id) on delete cascade,
  transaction_id uuid references transactions(id) on delete set null,
  state text default 'open', -- open | awaiting_reply | resolved | escalated
  question text,
  employee_response text,
  escalated_to_founder boolean default false,
  escalation_reason text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ─── Ask-Anything query cache ─────────────────────────────────
create table if not exists query_cache (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  question_hash text not null,
  question text,
  answer text,
  row_count integer,
  cached_at timestamptz default now(),
  expires_at timestamptz
);

-- ─── Indexes ──────────────────────────────────────────────────
create index if not exists idx_policies_company on policies(company_id, type);
create index if not exists idx_policy_actions_company on policy_actions(company_id, executed_at desc);
create index if not exists idx_neg_threads_company on negotiation_threads(company_id, state);
create index if not exists idx_restraint_company on restraint_log(company_id, created_at desc);
create index if not exists idx_emp_threads_company on employee_threads(company_id, state);
create index if not exists idx_query_cache on query_cache(company_id, question_hash, expires_at);

-- ─── flux_query RPC (safe read-only dynamic SQL) ──────────────
create or replace function flux_query(query_sql text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  result jsonb;
  normalized text;
begin
  normalized := lower(trim(query_sql));
  if not (normalized like 'select%') then
    raise exception 'flux_query: only SELECT statements are allowed';
  end if;
  execute 'select coalesce(jsonb_agg(q), ''[]''::jsonb) from ('
    || query_sql || ') q'
  into result;
  return coalesce(result, '[]'::jsonb);
end;
$$;

-- ─── Default policies for demo company ───────────────────────
insert into policies (company_id, type, enabled, threshold_amount, threshold_days, description)
values
  ('00000001-0000-4000-8000-000000000001', 'auto_cancel',          true, 100.0,  60, 'Auto-cancel subscriptions under $100/mo with 0 usage in 60 days'),
  ('00000001-0000-4000-8000-000000000001', 'auto_accept_discount', true, 5000.0, null, 'Auto-accept renewal discounts ≥10% on contracts under $5k'),
  ('00000001-0000-4000-8000-000000000001', 'auto_approve_expense', true, 200.0,  null, 'Auto-approve expenses matching previously-approved patterns (same merchant, same cap)'),
  ('00000001-0000-4000-8000-000000000001', 'production_infra',     true, null,   null, 'Never auto-approve production infrastructure vendors')
on conflict do nothing;

update policies
set production_infra_list = ARRAY[
  'AWS','GCP','Google Cloud','Azure','Cloudflare','Vercel','Railway',
  'Render','Fly.io','Heroku','DataDog','Sentry','PagerDuty',
  'New Relic','Fastly','Akamai'
]
where type = 'production_infra'
  and company_id = '00000001-0000-4000-8000-000000000001';

update policies
set threshold_discount_pct = 10.0
where type = 'auto_accept_discount'
  and company_id = '00000001-0000-4000-8000-000000000001';
