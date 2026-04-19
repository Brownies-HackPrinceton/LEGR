-- ============================================================
-- 007_machines.sql — Dedalus Machine registry
-- Tracks long-running Machine processes (negotiations, etc.)
-- ============================================================

CREATE TABLE IF NOT EXISTS active_machines (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  type TEXT NOT NULL,             -- 'negotiation' | 'seat_reclamation' | ...
  vendor TEXT,                    -- e.g. 'Cursor', 'Notion'
  thread_id UUID REFERENCES negotiation_threads(id) ON DELETE SET NULL,
  pid INTEGER,                    -- OS process ID for health checks
  spawned_at TIMESTAMPTZ DEFAULT now(),
  last_heartbeat TIMESTAMPTZ DEFAULT now(),
  state_path TEXT,                -- data/negotiations/cursor-2026-04.json
  status TEXT DEFAULT 'running',  -- running | sleeping | closed | crashed
  metadata JSONB DEFAULT '{}',
  closed_at TIMESTAMPTZ,
  outcome TEXT                    -- closed_won | closed_lost | stalled | killed
);

CREATE INDEX IF NOT EXISTS idx_machines_company ON active_machines(company_id, status);
CREATE INDEX IF NOT EXISTS idx_machines_status ON active_machines(status);
