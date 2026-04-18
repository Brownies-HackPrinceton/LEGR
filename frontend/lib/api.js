/**
 * Data fetchers — try Supabase first, fall back to mock data.js values.
 * The ORCHESTRATOR_URL env var points at FastAPI (default http://localhost:8000).
 */
import { supabase, hasSupabase } from './supabase.js';
import { metrics as mockMetrics, spendTrend as mockSpendTrend, activities as mockActivities } from '../data.js';

const COMPANY_ID = '00000001-0000-4000-8000-000000000001';
const ORCHESTRATOR = import.meta.env.VITE_ORCHESTRATOR_URL || 'http://localhost:8000';

// ── Transactions ──────────────────────────────────────────────────────────────

export async function fetchRecentTransactions(limit = 20) {
  if (!hasSupabase) return [];
  const { data } = await supabase
    .from('transactions')
    .select('*, employees(name, email)')
    .eq('company_id', COMPANY_ID)
    .order('created_at', { ascending: false })
    .limit(limit);
  return data || [];
}

// ── Alerts (Flux activity feed) ───────────────────────────────────────────────

export async function fetchAlerts(limit = 30) {
  if (!hasSupabase) return [];
  const { data } = await supabase
    .from('agent_alerts')
    .select('*')
    .eq('company_id', COMPANY_ID)
    .order('created_at', { ascending: false })
    .limit(limit);
  return data || [];
}

// ── Metrics (derived) ─────────────────────────────────────────────────────────

export async function fetchMetrics() {
  if (!hasSupabase) return mockMetrics;

  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();

  const [txnResp, seatResp, compResp, savingsResp] = await Promise.all([
    supabase.from('transactions').select('amount, pillar').eq('company_id', COMPANY_ID).gte('created_at', thirtyDaysAgo),
    supabase.from('seat_usage').select('id').eq('company_id', COMPANY_ID).eq('is_dormant', true),
    supabase.from('agent_alerts').select('id').eq('company_id', COMPANY_ID).eq('resolved', false).eq('requires_action', true),
    supabase.from('transactions').select('savings_identified').eq('company_id', COMPANY_ID),
  ]);

  const txns = txnResp.data || [];
  const totalMonthlySpend = txns.reduce((s, t) => s + parseFloat(t.amount || 0), 0);
  const identifiedSavings = (savingsResp.data || []).reduce((s, t) => s + parseFloat(t.savings_identified || 0), 0);

  return {
    ...mockMetrics,
    totalMonthlySpend: Math.round(totalMonthlySpend) || mockMetrics.totalMonthlySpend,
    identifiedSavings: Math.round(identifiedSavings) || mockMetrics.identifiedSavings,
    ghostSeats: (seatResp.data || []).length || mockMetrics.ghostSeats,
    complianceFlags: (compResp.data || []).length || mockMetrics.complianceFlags,
  };
}

// ── Spend trend ───────────────────────────────────────────────────────────────

export async function fetchSpendTrend() {
  if (!hasSupabase) return mockSpendTrend;

  // Build 14-day buckets
  const labels = [];
  const total = [], ai = [], saas = [], expenses = [];
  const now = new Date();

  for (let i = 13; i >= 0; i -= 2) {
    const d = new Date(now - i * 86400000);
    labels.push(d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
  }

  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
  const { data: txns } = await supabase
    .from('transactions')
    .select('amount, pillar, created_at')
    .eq('company_id', COMPANY_ID)
    .gte('created_at', thirtyDaysAgo);

  if (!txns || !txns.length) return mockSpendTrend;

  // Bucket by 2-day windows
  labels.forEach((_, idx) => {
    const from = new Date(now - (13 - idx * 2) * 86400000);
    const to = new Date(from.getTime() + 2 * 86400000);
    const bucket = txns.filter(t => {
      const d = new Date(t.created_at);
      return d >= from && d < to;
    });
    const sum = (p) => bucket.filter(t => t.pillar === p).reduce((s, t) => s + parseFloat(t.amount || 0), 0);
    const t = sum('ai_spend'), s = sum('saas_sprawl'), e = bucket.filter(t => t.pillar === 'compliance').reduce((acc, t) => acc + parseFloat(t.amount || 0), 0);
    ai.push(Math.round(t));
    saas.push(Math.round(s));
    expenses.push(Math.round(e));
    total.push(Math.round(t + s + e));
  });

  return { labels, datasets: { total, ai, saas, expenses } };
}

// ── Subscriptions ─────────────────────────────────────────────────────────────

export async function fetchSubscriptions() {
  if (!hasSupabase) return [];
  const { data } = await supabase
    .from('subscription_renewals')
    .select('*')
    .eq('company_id', COMPANY_ID)
    .order('renewal_date', { ascending: true });
  return data || [];
}

// ── Seat usage ────────────────────────────────────────────────────────────────

export async function fetchSeatUsage() {
  if (!hasSupabase) return [];
  const { data } = await supabase
    .from('seat_usage')
    .select('*, employees(name, role)')
    .eq('company_id', COMPANY_ID)
    .order('last_active_date', { ascending: true });
  return data || [];
}

// ── Policy actions ────────────────────────────────────────────────────────────

export async function fetchPolicyActions(limit = 10) {
  if (!hasSupabase) return [];
  const { data } = await supabase
    .from('policy_actions')
    .select('*')
    .eq('company_id', COMPANY_ID)
    .order('executed_at', { ascending: false })
    .limit(limit);
  return data || [];
}

// ── Ask Flux (NL query via orchestrator) ──────────────────────────────────────

export async function askFlux(question) {
  try {
    const r = await fetch(`${ORCHESTRATOR}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, company_id: COMPANY_ID }),
    });
    const json = await r.json();
    return json.answer || json.error || 'No answer';
  } catch (e) {
    return `Error: ${e.message}`;
  }
}

// ── Realtime subscription ─────────────────────────────────────────────────────

export function subscribeToAlerts(callback) {
  if (!hasSupabase) return () => {};
  const channel = supabase
    .channel('agent_alerts')
    .on('postgres_changes', {
      event: 'INSERT',
      schema: 'public',
      table: 'agent_alerts',
      filter: `company_id=eq.${COMPANY_ID}`,
    }, (payload) => callback(payload.new))
    .subscribe();

  return () => supabase.removeChannel(channel);
}
