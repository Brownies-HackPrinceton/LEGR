-- ============================================================
-- 008_knot_constraints.sql — Add missing unique constraints
--
-- The 007 migration uses CREATE TABLE IF NOT EXISTS, which
-- silently skips the UNIQUE clause when the table already
-- existed from a prior partial run. This migration adds the
-- constraints explicitly so ON CONFLICT upserts work.
-- Safe to re-run (DROP CONSTRAINT IF EXISTS).
-- ============================================================

-- knot_merchant_accounts: idempotency key for account upserts
alter table knot_merchant_accounts
  drop constraint if exists knot_merchant_accounts_external_user_id_merchant_id_key;

alter table knot_merchant_accounts
  add constraint knot_merchant_accounts_external_user_id_merchant_id_key
  unique (external_user_id, merchant_id);

-- knot_sync_cursors: idempotency key for cursor upserts
alter table knot_sync_cursors
  drop constraint if exists knot_sync_cursors_external_user_id_merchant_id_key;

alter table knot_sync_cursors
  add constraint knot_sync_cursors_external_user_id_merchant_id_key
  unique (external_user_id, merchant_id);
