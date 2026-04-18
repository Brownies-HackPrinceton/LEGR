-- SaaS sprawl services: overlaps, renewals, plan optimization, feature waste, shadow IT, savings log.
-- Idempotent: fixed UUIDs + ON CONFLICT (id) DO NOTHING. Apply after 001, 002, 003.

create table if not exists tool_overlaps (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  category text not null,
  tools text[] not null,
  total_monthly_cost numeric,
  recommended_consolidation text,
  estimated_savings numeric,
  detected_at timestamptz default now(),
  status text default 'pending'
);

create table if not exists subscription_renewals (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  vendor text not null,
  plan_tier text,
  monthly_cost numeric,
  annual_cost numeric,
  billing_cycle text,
  renewal_date date not null,
  auto_renew boolean default true,
  notice_period_days integer default 0,
  contract_terms text,
  last_negotiated_date date,
  next_action_date date,
  priority text
);

create table if not exists plan_optimization (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  vendor text not null,
  current_plan text,
  current_monthly_cost numeric,
  recommended_plan text,
  recommended_monthly_cost numeric,
  reason text,
  utilization_signals jsonb,
  confidence numeric,
  monthly_savings numeric,
  detected_at timestamptz default now(),
  status text default 'pending'
);

create table if not exists feature_waste (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  vendor text not null,
  feature text not null,
  monthly_cost numeric,
  usage_last_30d integer default 0,
  usage_last_90d integer default 0,
  first_enabled_date date,
  last_used_date date,
  recommendation text,
  confidence numeric,
  status text default 'open'
);

create table if not exists shadow_it (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  vendor text not null,
  first_charge_date date,
  monthly_cost numeric,
  charged_to_employee_id uuid references employees(id),
  purpose_declared text,
  approved boolean default false,
  risk_level text,
  security_concerns text[],
  detected_at timestamptz default now(),
  status text default 'flagged'
);

create table if not exists savings_log (
  id uuid default gen_random_uuid() primary key,
  company_id uuid references companies(id) on delete cascade,
  title text not null,
  amount_monthly numeric,
  status text not null default 'pending',
  source_type text,
  source_id uuid,
  created_at timestamptz default now()
);

create index if not exists idx_tool_overlaps_company on tool_overlaps(company_id, status);
create index if not exists idx_subscription_renewals_company on subscription_renewals(company_id, renewal_date);
create index if not exists idx_plan_optimization_company on plan_optimization(company_id, status);
create index if not exists idx_feature_waste_company on feature_waste(company_id, vendor);
create index if not exists idx_shadow_it_company on shadow_it(company_id, status);
create index if not exists idx_savings_log_company on savings_log(company_id, status);

-- Tool overlaps (6)
insert into tool_overlaps (
  id, company_id, category, tools, total_monthly_cost, recommended_consolidation, estimated_savings, detected_at, status
) values
  (
    '00000001-0000-4000-8000-000000007001',
    '00000001-0000-4000-8000-000000000001',
    'note_taking',
    array['Notion','Evernote','Roam']::text[],
    580,
    'Keep Notion as system of record; cancel Evernote + Roam.',
    100,
    '2026-04-17 10:00:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007002',
    '00000001-0000-4000-8000-000000000001',
    'video_conferencing',
    array['Zoom','Google Meet','Loom']::text[],
    259.90,
    'Keep Zoom for meetings; cancel Loom (Meet covered by Workspace).',
    80,
    '2026-04-17 10:05:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007003',
    '00000001-0000-4000-8000-000000000001',
    'project_mgmt',
    array['Linear','Asana']::text[],
    640,
    'Keep Linear; migrate remaining Asana boards.',
    240,
    '2026-04-17 10:10:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007004',
    '00000001-0000-4000-8000-000000000001',
    'communication',
    array['Slack','Discord']::text[],
    460,
    'Consolidate announcements to Slack; retire paid Discord servers.',
    100,
    '2026-04-17 10:12:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007005',
    '00000001-0000-4000-8000-000000000001',
    'design_handoff',
    array['Figma','Zeplin']::text[],
    890,
    'Use Figma Dev Mode / inspect; drop Zeplin.',
    90,
    '2026-04-17 10:15:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007006',
    '00000001-0000-4000-8000-000000000001',
    'analytics',
    array['Mixpanel','Amplitude','PostHog']::text[],
    459,
    'Consolidate on PostHog (self-serve + warehouse export).',
    380,
    '2026-04-17 10:18:00+00',
    'pending'
  )
on conflict (id) do nothing;

-- Subscription renewals (15)
insert into subscription_renewals (
  id, company_id, vendor, plan_tier, monthly_cost, annual_cost, billing_cycle, renewal_date, auto_renew,
  notice_period_days, contract_terms, last_negotiated_date, next_action_date, priority
) values
  ('00000001-0000-4000-8000-000000007010', '00000001-0000-4000-8000-000000000001', 'Cursor', 'Team', 1400, 16800, 'annual', '2026-04-24', true, 14, 'Annual prepaid; downgrade window 14d before renewal.', '2025-04-20', '2026-04-18', 'critical'),
  ('00000001-0000-4000-8000-000000007011', '00000001-0000-4000-8000-000000000001', 'Linear', 'Business', 400, null, 'monthly', '2026-04-28', true, 0, 'Month-to-month.', null, '2026-04-21', 'high'),
  ('00000001-0000-4000-8000-000000007012', '00000001-0000-4000-8000-000000000001', 'Notion', 'Business', 480, 5760, 'annual', '2026-05-03', true, 30, 'Annual with 30d cancellation notice.', '2025-05-01', '2026-04-18', 'high'),
  ('00000001-0000-4000-8000-000000007013', '00000001-0000-4000-8000-000000000001', 'Figma', 'Organization', 800, 9600, 'annual', '2026-05-15', true, 30, 'Enterprise agreement draft on file.', '2025-05-10', '2026-04-25', 'high'),
  ('00000001-0000-4000-8000-000000007014', '00000001-0000-4000-8000-000000000001', 'Vercel', 'Pro', 240, null, 'monthly', '2026-05-18', true, 0, 'Usage-based overages possible.', null, '2026-05-11', 'normal'),
  ('00000001-0000-4000-8000-000000007015', '00000001-0000-4000-8000-000000000001', 'Slack', 'Business+', 360, 4320, 'annual', '2026-06-01', true, 30, 'Must notify by T-30 to avoid auto-renew.', '2025-06-01', '2026-05-02', 'high'),
  ('00000001-0000-4000-8000-000000007016', '00000001-0000-4000-8000-000000000001', 'GitHub', 'Enterprise', 210, 2520, 'annual', '2026-06-10', true, 30, 'GitHub Enterprise renewal.', '2025-06-12', '2026-05-27', 'normal'),
  ('00000001-0000-4000-8000-000000007017', '00000001-0000-4000-8000-000000000001', 'AWS Marketplace', 'Vendor bundle A', 287, 3444, 'annual', '2026-05-07', true, 30, 'Third-party AMI + support package.', null, '2026-04-22', 'high'),
  ('00000001-0000-4000-8000-000000007018', '00000001-0000-4000-8000-000000000001', 'AWS Marketplace', 'Security scanner', 198, 2376, 'annual', '2026-06-22', true, 14, 'Annual commit.', null, '2026-06-08', 'normal'),
  ('00000001-0000-4000-8000-000000007019', '00000001-0000-4000-8000-000000000001', 'AWS Marketplace', 'Data connector', 341, 4092, 'annual', '2026-07-09', true, 30, 'ETL connector subscription.', null, '2026-06-09', 'normal'),
  ('00000001-0000-4000-8000-000000007020', '00000001-0000-4000-8000-000000000001', '1Password', 'Business', 119.40, 1432.80, 'annual', '2026-05-22', true, 14, 'Per-seat annual.', '2025-05-22', '2026-05-15', 'normal'),
  ('00000001-0000-4000-8000-000000007021', '00000001-0000-4000-8000-000000000001', 'Sentry', 'Business', 180, 2160, 'annual', '2026-06-04', true, 30, 'Error monitoring annual.', '2025-06-04', '2026-05-19', 'normal'),
  ('00000001-0000-4000-8000-000000007022', '00000001-0000-4000-8000-000000000001', 'Datadog', 'Pro', 420, 5040, 'annual', '2026-06-15', true, 60, 'Infra + APM bundle; long notice for downgrade.', '2025-06-15', '2026-04-16', 'high'),
  ('00000001-0000-4000-8000-000000007023', '00000001-0000-4000-8000-000000000001', 'Mailchimp', 'Standard', 89.50, null, 'monthly', '2026-05-12', true, 0, 'Marketing email tier.', null, '2026-05-05', 'normal'),
  ('00000001-0000-4000-8000-000000007024', '00000001-0000-4000-8000-000000000001', 'Intercom', 'Pro', 540, 6480, 'annual', '2026-07-01', true, 60, 'Support inbox; cancel notice 60d.', '2025-07-01', '2026-05-02', 'high')
on conflict (id) do nothing;

-- Plan optimizations (8)
insert into plan_optimization (
  id, company_id, vendor, current_plan, current_monthly_cost, recommended_plan, recommended_monthly_cost,
  reason, utilization_signals, confidence, monthly_savings, detected_at, status
) values
  (
    '00000001-0000-4000-8000-000000007030',
    '00000001-0000-4000-8000-000000000001',
    'Notion',
    'Business',
    480,
    'Team',
    200,
    'No SAML, SCIM, or advanced permissions usage in 90d.',
    '{"saml_logins_30d": 0, "scim_events_30d": 0, "advanced_permissions_used": false, "audit_log_queries_30d": 0}'::jsonb,
    0.88,
    280,
    '2026-04-16 09:00:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007031',
    '00000001-0000-4000-8000-000000000001',
    'Linear',
    'Business',
    400,
    'Standard',
    280,
    'Team under 25 seats; Business-only features unused.',
    '{"business_only_views_used": false, "issue_templates_advanced": 0}'::jsonb,
    0.82,
    120,
    '2026-04-16 09:05:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007032',
    '00000001-0000-4000-8000-000000000001',
    'Slack',
    'Business+',
    360,
    'Pro',
    180,
    'No compliance exports or discovery hold usage.',
    '{"compliance_exports_90d": 0, "legal_hold_enabled": false}'::jsonb,
    0.79,
    180,
    '2026-04-16 09:10:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007033',
    '00000001-0000-4000-8000-000000000001',
    'Vercel',
    'Pro',
    240,
    'Hobby',
    220,
    'Staging project has near-zero traffic vs prod.',
    '{"staging_rps_p95": 0.02, "bandwidth_gb_30d": 1.1}'::jsonb,
    0.74,
    20,
    '2026-04-16 09:12:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007034',
    '00000001-0000-4000-8000-000000000001',
    'GitHub',
    'Enterprise',
    210,
    'Team',
    120,
    'Advanced security features not configured.',
    '{"secret_scanning_custom_patterns": 0, "code_scanning_alerts_resolved_30d": 0}'::jsonb,
    0.71,
    90,
    '2026-04-16 09:15:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007035',
    '00000001-0000-4000-8000-000000000001',
    'Zoom',
    'Business',
    199.90,
    'Pro',
    159.90,
    'Max 3 concurrent large meetings; Business tier overkill.',
    '{"concurrent_large_meetings_max": 3, "webinar_addon_active": false}'::jsonb,
    0.69,
    40,
    '2026-04-16 09:18:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007036',
    '00000001-0000-4000-8000-000000000001',
    '1Password',
    'Business',
    119.40,
    'Teams',
    79.60,
    'Under 10 seats; Teams SKU fits current headcount.',
    '{"seats_active": 8, "business_only_policies_used": false}'::jsonb,
    0.77,
    39.80,
    '2026-04-16 09:20:00+00',
    'pending'
  ),
  (
    '00000001-0000-4000-8000-000000007037',
    '00000001-0000-4000-8000-000000000001',
    'Datadog',
    'Pro',
    420,
    'Free',
    340,
    'Dev-only hosts have no production traffic monitored.',
    '{"dev_hosts_prod_traces_30d": 0, "apm_hosts_dev": 4}'::jsonb,
    0.73,
    80,
    '2026-04-16 09:22:00+00',
    'pending'
  )
on conflict (id) do nothing;

-- Feature waste (10)
insert into feature_waste (
  id, company_id, vendor, feature, monthly_cost, usage_last_30d, usage_last_90d, first_enabled_date, last_used_date,
  recommendation, confidence, status
) values
  ('00000001-0000-4000-8000-000000007040', '00000001-0000-4000-8000-000000000001', 'Figma', 'Dev Mode', 150, 0, 2, '2025-08-01', '2026-02-15', 'disable', 0.91, 'open'),
  ('00000001-0000-4000-8000-000000007041', '00000001-0000-4000-8000-000000000001', 'Linear', 'Insights', 80, 1, 3, '2025-11-10', '2026-03-02', 'disable', 0.86, 'open'),
  ('00000001-0000-4000-8000-000000007042', '00000001-0000-4000-8000-000000000001', 'Notion', 'Notion AI', 160, 12, 41, '2025-09-01', '2026-04-10', 'downgrade', 0.84, 'open'),
  ('00000001-0000-4000-8000-000000007043', '00000001-0000-4000-8000-000000000001', 'GitHub', 'Copilot Business', 190, 412, 1288, '2025-06-01', '2026-04-16', 'downgrade', 0.89, 'open'),
  ('00000001-0000-4000-8000-000000007044', '00000001-0000-4000-8000-000000000001', 'Slack', 'Workflow Builder premium', 40, 0, 0, '2025-10-01', null, 'disable', 0.93, 'open'),
  ('00000001-0000-4000-8000-000000007045', '00000001-0000-4000-8000-000000000001', 'Vercel', 'Analytics', 50, 0, 1, '2025-12-01', '2026-03-11', 'disable', 0.88, 'open'),
  ('00000001-0000-4000-8000-000000007046', '00000001-0000-4000-8000-000000000001', 'Datadog', 'APM add-on', 200, 1200, 4100, '2025-04-01', '2026-04-14', 'downgrade', 0.81, 'open'),
  ('00000001-0000-4000-8000-000000007047', '00000001-0000-4000-8000-000000000001', 'Zoom', 'Webinar 500', 70, 0, 0, '2025-07-01', '2026-01-05', 'disable', 0.9, 'open'),
  ('00000001-0000-4000-8000-000000007048', '00000001-0000-4000-8000-000000000001', 'Calendly', 'Premium routing', 60, 0, 2, '2025-05-01', '2026-02-28', 'downgrade', 0.85, 'open'),
  ('00000001-0000-4000-8000-000000007049', '00000001-0000-4000-8000-000000000001', 'HubSpot', 'Marketing Hub Pro', 400, 820, 2400, '2025-03-01', '2026-04-12', 'downgrade', 0.8, 'open')
on conflict (id) do nothing;

-- Shadow IT (7) — employees: Marcus 011, Priya 014, Tom 013, Jordan 015, Casey 016, Sarah 010, Alex 012
insert into shadow_it (
  id, company_id, vendor, first_charge_date, monthly_cost, charged_to_employee_id, purpose_declared, approved, risk_level, security_concerns, detected_at, status
) values
  (
    '00000001-0000-4000-8000-000000007050',
    '00000001-0000-4000-8000-000000000001',
    'ChatGPT Plus',
    '2025-11-04',
    20,
    '00000001-0000-4000-8000-000000000011',
    'Personal productivity experiments',
    false,
    'low',
    array['no_sso', 'no_security_review']::text[],
    '2026-04-14 08:00:00+00',
    'flagged'
  ),
  (
    '00000001-0000-4000-8000-000000007051',
    '00000001-0000-4000-8000-000000000001',
    'Cursor',
    '2026-01-08',
    20,
    '00000001-0000-4000-8000-000000000014',
    'Personal Pro on top of company seat',
    false,
    'low',
    array['duplicate_license', 'no_security_review']::text[],
    '2026-04-14 08:05:00+00',
    'flagged'
  ),
  (
    '00000001-0000-4000-8000-000000007052',
    '00000001-0000-4000-8000-000000000001',
    'Apollo.io',
    '2025-10-19',
    149,
    '00000001-0000-4000-8000-000000000013',
    'Outbound prospecting',
    false,
    'medium',
    array['stores_customer_data', 'no_sso', 'third_party_integrations_unknown']::text[],
    '2026-04-14 08:10:00+00',
    'flagged'
  ),
  (
    '00000001-0000-4000-8000-000000007053',
    '00000001-0000-4000-8000-000000000001',
    'Replit',
    '2025-12-02',
    15,
    '00000001-0000-4000-8000-000000000015',
    'Side prototypes',
    false,
    'low',
    array['no_security_review']::text[],
    '2026-04-14 08:12:00+00',
    'flagged'
  ),
  (
    '00000001-0000-4000-8000-000000007054',
    '00000001-0000-4000-8000-000000000001',
    'Dribbble',
    '2025-09-14',
    20,
    '00000001-0000-4000-8000-000000000016',
    'Portfolio visibility',
    false,
    'low',
    array['personal_use', 'no_sso']::text[],
    '2026-04-14 08:14:00+00',
    'flagged'
  ),
  (
    '00000001-0000-4000-8000-000000007055',
    '00000001-0000-4000-8000-000000000001',
    'Framer',
    '2026-02-01',
    45,
    '00000001-0000-4000-8000-000000000010',
    'Marketing microsite experiments',
    false,
    'medium',
    array['might_overlap_design_stack', 'no_security_review']::text[],
    '2026-04-14 08:16:00+00',
    'flagged'
  ),
  (
    '00000001-0000-4000-8000-000000007056',
    '00000001-0000-4000-8000-000000000001',
    'ClickUp',
    '2025-08-21',
    19,
    '00000001-0000-4000-8000-000000000012',
    'Personal task backlog',
    false,
    'medium',
    array['duplicate_project_mgmt', 'no_sso']::text[],
    '2026-04-14 08:18:00+00',
    'flagged'
  )
on conflict (id) do nothing;

-- Savings log (pending) — mirrors key opportunities + new alerts
insert into savings_log (id, company_id, title, amount_monthly, status, source_type, source_id, created_at) values
  ('00000001-0000-4000-8000-000000007060', '00000001-0000-4000-8000-000000000001', 'Analytics stack consolidation (PostHog)', 380, 'pending', 'tool_overlap', '00000001-0000-4000-8000-000000007006', '2026-04-17 11:00:00+00'),
  ('00000001-0000-4000-8000-000000007061', '00000001-0000-4000-8000-000000000001', 'Slack renewal decision window (30d notice)', 0, 'pending', 'subscription_renewal', '00000001-0000-4000-8000-000000007015', '2026-04-17 11:02:00+00'),
  ('00000001-0000-4000-8000-000000007062', '00000001-0000-4000-8000-000000000001', 'Notion Business → Team tier', 280, 'pending', 'plan_optimization', '00000001-0000-4000-8000-000000007030', '2026-04-17 11:04:00+00'),
  ('00000001-0000-4000-8000-000000007063', '00000001-0000-4000-8000-000000000001', 'GitHub Copilot seat right-size', 114, 'pending', 'feature_waste', '00000001-0000-4000-8000-000000007043', '2026-04-17 11:06:00+00'),
  ('00000001-0000-4000-8000-000000007064', '00000001-0000-4000-8000-000000000001', 'Apollo.io shadow IT review', 149, 'pending', 'shadow_it', '00000001-0000-4000-8000-000000007052', '2026-04-17 11:08:00+00'),
  ('00000001-0000-4000-8000-000000007065', '00000001-0000-4000-8000-000000000001', 'Note-taking overlap cleanup', 100, 'pending', 'tool_overlap', '00000001-0000-4000-8000-000000007001', '2026-04-17 11:10:00+00'),
  ('00000001-0000-4000-8000-000000007066', '00000001-0000-4000-8000-000000000001', 'Design handoff (Zeplin)', 90, 'pending', 'tool_overlap', '00000001-0000-4000-8000-000000007005', '2026-04-17 11:12:00+00')
on conflict (id) do nothing;

-- Transactions: overlap tools (6 months each) + shadow charges + HubSpot/Calendly for feature waste
insert into transactions (
  id, company_id, created_at, merchant, amount, category, submitted_by, employee_id, memo, status, pillar,
  agent_assigned, agent_reasoning, agent_output, founder_action, savings_identified
) values
  ('00000001-0000-4000-8000-000000008001', '00000001-0000-4000-8000-000000000001', '2025-11-04 11:00:00+00', 'Evernote', 59.99, 'saas', 'system', null, 'Professional plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008002', '00000001-0000-4000-8000-000000000001', '2025-12-04 11:00:00+00', 'Evernote', 59.99, 'saas', 'system', null, 'Professional plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008003', '00000001-0000-4000-8000-000000000001', '2026-01-06 11:00:00+00', 'Evernote', 59.99, 'saas', 'system', null, 'Professional plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008004', '00000001-0000-4000-8000-000000000001', '2026-02-04 11:00:00+00', 'Evernote', 59.99, 'saas', 'system', null, 'Professional plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008005', '00000001-0000-4000-8000-000000000001', '2026-03-04 11:00:00+00', 'Evernote', 59.99, 'saas', 'system', null, 'Professional plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008006', '00000001-0000-4000-8000-000000000001', '2026-04-04 11:00:00+00', 'Evernote', 59.99, 'saas', 'system', null, 'Professional plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008007', '00000001-0000-4000-8000-000000000001', '2025-11-05 11:00:00+00', 'Roam', 39, 'saas', 'system', null, 'Believer plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008008', '00000001-0000-4000-8000-000000000001', '2025-12-05 11:00:00+00', 'Roam', 39, 'saas', 'system', null, 'Believer plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008009', '00000001-0000-4000-8000-000000000001', '2026-01-05 11:00:00+00', 'Roam', 39, 'saas', 'system', null, 'Believer plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008010', '00000001-0000-4000-8000-000000000001', '2026-02-05 11:00:00+00', 'Roam', 39, 'saas', 'system', null, 'Believer plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008011', '00000001-0000-4000-8000-000000000001', '2026-03-05 11:00:00+00', 'Roam', 39, 'saas', 'system', null, 'Believer plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008012', '00000001-0000-4000-8000-000000000001', '2026-04-05 11:00:00+00', 'Roam', 39, 'saas', 'system', null, 'Believer plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008013', '00000001-0000-4000-8000-000000000001', '2025-11-06 11:00:00+00', 'Asana', 239.88, 'saas', 'system', null, 'Business tier — legacy pod', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008014', '00000001-0000-4000-8000-000000000001', '2025-12-06 11:00:00+00', 'Asana', 239.88, 'saas', 'system', null, 'Business tier — legacy pod', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008015', '00000001-0000-4000-8000-000000000001', '2026-01-06 11:00:00+00', 'Asana', 239.88, 'saas', 'system', null, 'Business tier — legacy pod', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008016', '00000001-0000-4000-8000-000000000001', '2026-02-06 11:00:00+00', 'Asana', 239.88, 'saas', 'system', null, 'Business tier — legacy pod', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008017', '00000001-0000-4000-8000-000000000001', '2026-03-06 11:00:00+00', 'Asana', 239.88, 'saas', 'system', null, 'Business tier — legacy pod', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008018', '00000001-0000-4000-8000-000000000001', '2026-04-06 11:00:00+00', 'Asana', 239.88, 'saas', 'system', null, 'Business tier — legacy pod', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008019', '00000001-0000-4000-8000-000000000001', '2025-11-07 11:00:00+00', 'Discord', 99.50, 'saas', 'system', null, 'Nitro + 2 boosted servers', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008020', '00000001-0000-4000-8000-000000000001', '2025-12-07 11:00:00+00', 'Discord', 99.50, 'saas', 'system', null, 'Nitro + 2 boosted servers', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008021', '00000001-0000-4000-8000-000000000001', '2026-01-07 11:00:00+00', 'Discord', 99.50, 'saas', 'system', null, 'Nitro + 2 boosted servers', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008022', '00000001-0000-4000-8000-000000000001', '2026-02-07 11:00:00+00', 'Discord', 99.50, 'saas', 'system', null, 'Nitro + 2 boosted servers', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008023', '00000001-0000-4000-8000-000000000001', '2026-03-07 11:00:00+00', 'Discord', 99.50, 'saas', 'system', null, 'Nitro + 2 boosted servers', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008024', '00000001-0000-4000-8000-000000000001', '2026-04-07 11:00:00+00', 'Discord', 99.50, 'saas', 'system', null, 'Nitro + 2 boosted servers', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008025', '00000001-0000-4000-8000-000000000001', '2025-11-08 11:00:00+00', 'Zeplin', 89, 'saas', 'system', null, 'Organization plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008026', '00000001-0000-4000-8000-000000000001', '2025-12-08 11:00:00+00', 'Zeplin', 89, 'saas', 'system', null, 'Organization plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008027', '00000001-0000-4000-8000-000000000001', '2026-01-08 11:00:00+00', 'Zeplin', 89, 'saas', 'system', null, 'Organization plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008028', '00000001-0000-4000-8000-000000000001', '2026-02-08 11:00:00+00', 'Zeplin', 89, 'saas', 'system', null, 'Organization plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008029', '00000001-0000-4000-8000-000000000001', '2026-03-08 11:00:00+00', 'Zeplin', 89, 'saas', 'system', null, 'Organization plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008030', '00000001-0000-4000-8000-000000000001', '2026-04-08 11:00:00+00', 'Zeplin', 89, 'saas', 'system', null, 'Organization plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008031', '00000001-0000-4000-8000-000000000001', '2025-11-09 11:00:00+00', 'Mixpanel', 199, 'saas', 'system', null, 'Growth plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008032', '00000001-0000-4000-8000-000000000001', '2025-12-09 11:00:00+00', 'Mixpanel', 199, 'saas', 'system', null, 'Growth plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008033', '00000001-0000-4000-8000-000000000001', '2026-01-09 11:00:00+00', 'Mixpanel', 199, 'saas', 'system', null, 'Growth plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008034', '00000001-0000-4000-8000-000000000001', '2026-02-09 11:00:00+00', 'Mixpanel', 199, 'saas', 'system', null, 'Growth plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008035', '00000001-0000-4000-8000-000000000001', '2026-03-09 11:00:00+00', 'Mixpanel', 199, 'saas', 'system', null, 'Growth plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008036', '00000001-0000-4000-8000-000000000001', '2026-04-09 11:00:00+00', 'Mixpanel', 199, 'saas', 'system', null, 'Growth plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008037', '00000001-0000-4000-8000-000000000001', '2025-11-10 11:00:00+00', 'Amplitude', 179.25, 'saas', 'system', null, 'Plus plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008038', '00000001-0000-4000-8000-000000000001', '2025-12-10 11:00:00+00', 'Amplitude', 179.25, 'saas', 'system', null, 'Plus plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008039', '00000001-0000-4000-8000-000000000001', '2026-01-10 11:00:00+00', 'Amplitude', 179.25, 'saas', 'system', null, 'Plus plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008040', '00000001-0000-4000-8000-000000000001', '2026-02-10 11:00:00+00', 'Amplitude', 179.25, 'saas', 'system', null, 'Plus plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008041', '00000001-0000-4000-8000-000000000001', '2026-03-10 11:00:00+00', 'Amplitude', 179.25, 'saas', 'system', null, 'Plus plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008042', '00000001-0000-4000-8000-000000000001', '2026-04-10 11:00:00+00', 'Amplitude', 179.25, 'saas', 'system', null, 'Plus plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008043', '00000001-0000-4000-8000-000000000001', '2025-11-11 11:00:00+00', 'PostHog', 79.20, 'saas', 'system', null, 'Scale — event volume tier', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008044', '00000001-0000-4000-8000-000000000001', '2025-12-11 11:00:00+00', 'PostHog', 79.20, 'saas', 'system', null, 'Scale — event volume tier', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008045', '00000001-0000-4000-8000-000000000001', '2026-01-11 11:00:00+00', 'PostHog', 79.20, 'saas', 'system', null, 'Scale — event volume tier', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008046', '00000001-0000-4000-8000-000000000001', '2026-02-11 11:00:00+00', 'PostHog', 79.20, 'saas', 'system', null, 'Scale — event volume tier', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008047', '00000001-0000-4000-8000-000000000001', '2026-03-11 11:00:00+00', 'PostHog', 79.20, 'saas', 'system', null, 'Scale — event volume tier', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008048', '00000001-0000-4000-8000-000000000001', '2026-04-11 11:00:00+00', 'PostHog', 79.20, 'saas', 'system', null, 'Scale — event volume tier', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008049', '00000001-0000-4000-8000-000000000001', '2025-11-12 11:00:00+00', 'Loom', 79, 'saas', 'system', null, 'Business — 12 creator licenses', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008050', '00000001-0000-4000-8000-000000000001', '2025-12-12 11:00:00+00', 'Loom', 79, 'saas', 'system', null, 'Business — 12 creator licenses', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008051', '00000001-0000-4000-8000-000000000001', '2026-01-12 11:00:00+00', 'Loom', 79, 'saas', 'system', null, 'Business — 12 creator licenses', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008052', '00000001-0000-4000-8000-000000000001', '2026-02-12 11:00:00+00', 'Loom', 79, 'saas', 'system', null, 'Business — 12 creator licenses', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008053', '00000001-0000-4000-8000-000000000001', '2026-03-12 11:00:00+00', 'Loom', 79, 'saas', 'system', null, 'Business — 12 creator licenses', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008054', '00000001-0000-4000-8000-000000000001', '2026-04-12 11:00:00+00', 'Loom', 79, 'saas', 'system', null, 'Business — 12 creator licenses', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008055', '00000001-0000-4000-8000-000000000001', '2026-04-01 09:00:00+00', 'Google Workspace', 0, 'saas', 'system', null, 'Meet included in Workspace (no incremental line item)', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008056', '00000001-0000-4000-8000-000000000001', '2026-04-14 12:00:00+00', 'ChatGPT Plus', 20, 'software', 'employee', '00000001-0000-4000-8000-000000000011', 'OpenAI consumer subscription', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008057', '00000001-0000-4000-8000-000000000001', '2026-04-08 12:00:00+00', 'Cursor', 20, 'software', 'employee', '00000001-0000-4000-8000-000000000014', 'Cursor Pro — duplicate of company seat', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008058', '00000001-0000-4000-8000-000000000001', '2026-04-10 12:00:00+00', 'Apollo.io', 149, 'software', 'employee', '00000001-0000-4000-8000-000000000013', 'Sales outbound data — card on file', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008059', '00000001-0000-4000-8000-000000000001', '2026-04-07 12:00:00+00', 'Replit', 15, 'software', 'employee', '00000001-0000-4000-8000-000000000015', 'Hacker plan', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008060', '00000001-0000-4000-8000-000000000001', '2026-04-11 12:00:00+00', 'Dribbble', 20, 'software', 'employee', '00000001-0000-4000-8000-000000000016', 'Pro portfolio', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008061', '00000001-0000-4000-8000-000000000001', '2026-04-09 12:00:00+00', 'Framer', 45, 'software', 'employee', '00000001-0000-4000-8000-000000000010', 'Site experiments', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008062', '00000001-0000-4000-8000-000000000001', '2026-04-06 12:00:00+00', 'ClickUp', 19, 'software', 'employee', '00000001-0000-4000-8000-000000000012', 'Unlimited tier — personal space', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008063', '00000001-0000-4000-8000-000000000001', '2025-11-14 11:00:00+00', 'HubSpot', 397.50, 'saas', 'system', null, 'Marketing Hub Pro', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008064', '00000001-0000-4000-8000-000000000001', '2025-12-14 11:00:00+00', 'HubSpot', 397.50, 'saas', 'system', null, 'Marketing Hub Pro', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008065', '00000001-0000-4000-8000-000000000001', '2026-01-14 11:00:00+00', 'HubSpot', 397.50, 'saas', 'system', null, 'Marketing Hub Pro', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008066', '00000001-0000-4000-8000-000000000001', '2026-02-14 11:00:00+00', 'HubSpot', 397.50, 'saas', 'system', null, 'Marketing Hub Pro', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008067', '00000001-0000-4000-8000-000000000001', '2026-03-14 11:00:00+00', 'HubSpot', 397.50, 'saas', 'system', null, 'Marketing Hub Pro', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008068', '00000001-0000-4000-8000-000000000001', '2026-04-14 11:00:00+00', 'HubSpot', 397.50, 'saas', 'system', null, 'Marketing Hub Pro', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008069', '00000001-0000-4000-8000-000000000001', '2025-11-15 11:00:00+00', 'Calendly', 59.40, 'saas', 'system', null, 'Teams + routing premium', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008070', '00000001-0000-4000-8000-000000000001', '2025-12-15 11:00:00+00', 'Calendly', 59.40, 'saas', 'system', null, 'Teams + routing premium', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008071', '00000001-0000-4000-8000-000000000001', '2026-01-15 11:00:00+00', 'Calendly', 59.40, 'saas', 'system', null, 'Teams + routing premium', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008072', '00000001-0000-4000-8000-000000000001', '2026-02-15 11:00:00+00', 'Calendly', 59.40, 'saas', 'system', null, 'Teams + routing premium', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008073', '00000001-0000-4000-8000-000000000001', '2026-03-15 11:00:00+00', 'Calendly', 59.40, 'saas', 'system', null, 'Teams + routing premium', 'posted', 'saas_sprawl', null, null, null, null, 0),
  ('00000001-0000-4000-8000-000000008074', '00000001-0000-4000-8000-000000000001', '2026-04-15 11:00:00+00', 'Calendly', 59.40, 'saas', 'system', null, 'Teams + routing premium', 'posted', 'saas_sprawl', null, null, null, null, 0)
on conflict (id) do nothing;

-- Agent alerts (5 new actionable)
insert into agent_alerts (
  id, company_id, created_at, transaction_id, pillar, alert_type, message, requires_action, action_prompt, resolved, resolved_at
) values
  (
    '00000001-0000-4000-8000-000000007080',
    '00000001-0000-4000-8000-000000000001',
    '2026-04-17 12:00:00+00',
    '00000001-0000-4000-8000-000000008048',
    'saas_sprawl',
    'duplicate_tool',
    'Paying for Mixpanel + Amplitude + PostHog. PostHog is cheaper and self-serve. Consolidate? $380/mo savings.',
    true,
    'Consolidate analytics on PostHog?',
    false,
    null
  ),
  (
    '00000001-0000-4000-8000-000000007081',
    '00000001-0000-4000-8000-000000000001',
    '2026-04-17 12:05:00+00',
    '00000001-0000-4000-8000-000000000256',
    'saas_sprawl',
    'renewal_warning',
    'Slack renews in 44 days but needs 30-day cancel notice. Decide by 2026-05-02. Keep Business+ at $360/mo or downgrade?',
    true,
    'Open Slack renewal decision?',
    false,
    null
  ),
  (
    '00000001-0000-4000-8000-000000007082',
    '00000001-0000-4000-8000-000000000001',
    '2026-04-17 12:10:00+00',
    '00000001-0000-4000-8000-000000000242',
    'saas_sprawl',
    'tier_mismatch',
    'Notion on Business tier ($480/mo) but you are not using SAML, SCIM, or advanced permissions. Team tier ≈ $200/mo saves $280/mo.',
    true,
    'Downgrade Notion to Team?',
    false,
    null
  ),
  (
    '00000001-0000-4000-8000-000000007083',
    '00000001-0000-4000-8000-000000000001',
    '2026-04-17 12:15:00+00',
    '00000001-0000-4000-8000-00000000025b',
    'saas_sprawl',
    'feature_waste',
    'GitHub Copilot Business: 6 of 10 seats have not triggered a completion in 30 days. Drop to 4 seats saves $114/mo.',
    true,
    'Right-size Copilot seats?',
    false,
    null
  ),
  (
    '00000001-0000-4000-8000-000000007084',
    '00000001-0000-4000-8000-000000000001',
    '2026-04-17 12:20:00+00',
    '00000001-0000-4000-8000-000000008058',
    'saas_sprawl',
    'shadow_it',
    'Tom R swiped Apollo.io $149/mo — no IT review, stores customer data. Approve, cancel, or migrate to company account?',
    true,
    'Review Apollo.io with Tom?',
    false,
    null
  )
on conflict (id) do nothing;
