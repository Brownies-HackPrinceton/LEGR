-- Negotiation history: store prior renewal negotiation threads/outcomes for tone + leverage.
-- Idempotent: fixed UUIDs + ON CONFLICT (id) DO NOTHING.

create table if not exists negotiation_history (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  vendor text not null,
  initiated_date timestamptz default now(),
  original_price numeric,
  target_discount numeric,
  outcome text default 'ongoing', -- ongoing | won | lost
  thread_summary text
);

create index if not exists idx_negotiation_history_company on negotiation_history(company_id, vendor, initiated_date desc);

-- Seed: a few prior "won" negotiations for tone reference.
insert into negotiation_history (
  id, company_id, vendor, initiated_date, original_price, target_discount, outcome, thread_summary
) values
  (
    '00000001-0000-4000-8000-000000009001',
    '00000001-0000-4000-8000-000000000001',
    'Cursor',
    '2025-04-20 09:00:00+00',
    1600,
    15,
    'won',
    'Renewal: asked for 15% discount citing budget constraints + annual commitment; vendor agreed with 12-month term.'
  ),
  (
    '00000001-0000-4000-8000-000000009002',
    '00000001-0000-4000-8000-000000000001',
    'Slack',
    '2025-06-01 09:00:00+00',
    420,
    10,
    'won',
    'Renewal: requested 10% reduction and seat flexibility; vendor offered 10% off plus 60-day true-down window.'
  ),
  (
    '00000001-0000-4000-8000-000000009003',
    '00000001-0000-4000-8000-000000000001',
    'Notion',
    '2025-05-01 09:00:00+00',
    520,
    12,
    'won',
    'Renewal: negotiated down tier and removed unused add-ons after usage review; saved $250/mo equivalent.'
  )
on conflict (id) do nothing;

