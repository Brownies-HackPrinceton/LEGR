create table companies (
  id uuid default gen_random_uuid() primary key,
  name text not null,
  founder_email text,
  monthly_budget numeric default 50000,
  created_at timestamptz default now()
);

create table employees (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  name text not null,
  email text unique not null,
  role text,
  monthly_expense_cap numeric default 400,
  created_at timestamptz default now()
);

create table transactions (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  created_at timestamptz default now(),
  merchant text not null,
  amount numeric not null,
  category text,
  submitted_by text,
  employee_id uuid references employees(id),
  memo text,
  status text default 'pending',
  pillar text,
  agent_assigned text,
  agent_reasoning text,
  agent_output jsonb,
  founder_action text,
  savings_identified numeric default 0
);

create table seat_usage (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  employee_id uuid references employees(id),
  tool text not null,
  last_active_date date,
  confidence_score numeric,
  signal_sources text[],
  commits_last_30d integer default 0,
  calendar_blocks integer default 0,
  gmail_notifications integer default 0,
  is_dormant boolean default false,
  checked_at timestamptz default now()
);

create table ai_usage (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  week_start date,
  vendor text,
  model text,
  call_count integer,
  total_tokens integer,
  total_cost numeric,
  use_case text,
  recommended_model text,
  potential_savings numeric
);

create table agent_alerts (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  created_at timestamptz default now(),
  transaction_id uuid references transactions(id) on delete cascade,
  pillar text,
  alert_type text,
  message text,
  requires_action boolean default false,
  action_prompt text,
  resolved boolean default false,
  resolved_at timestamptz
);

create index idx_txn_company on transactions(company_id, created_at desc);
create index idx_alerts_company on agent_alerts(company_id, created_at desc);
create index idx_seat_tool on seat_usage(company_id, tool);

alter publication supabase_realtime add table transactions;
alter publication supabase_realtime add table agent_alerts;
