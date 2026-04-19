// ============================================================
// CONNECT — Knot integration UI
//
// All sensitive operations happen on the orchestrator. The browser:
//   1. Loads available merchants for the current platform
//   2. Lets the user pick one
//   3. Asks orchestrator for a session_id, then opens the Knot Web SDK
//   4. After AUTHENTICATED webhook fires, the linked-account row appears
//   5. "Sync now" triggers POST /knot/sync
//   6. "Simulate link (dev)" calls the dev endpoint to generate sample data
//
// Frontend prints high-level UI state. Detailed activity (env vars, SDK
// session ids, login/logout, sync pages, webhook events) is logged to the
// orchestrator stdout — never to the browser console.
// ============================================================

import {
  fetchKnotConfig,
  fetchKnotMerchants,
  fetchKnotAccounts,
  fetchKnotSyncLog,
  fetchKnotWebhookEvents,
  fetchKnotHealth,
  createKnotSession,
  triggerKnotSync,
  devSimulateLink,
  openKnotSDK,
  knotSdkAvailable,
} from '../lib/knot.js';

let state = {
  config: null,
  health: null,
  merchants: [],
  accounts: [],
  syncLog: [],
  webhooks: [],
  selectedMerchant: null,
  filter: '',
  busy: null, // string: which button is currently busy
  toast: null,
};

export function renderConnect() {
  return `
    <div class="page" id="page-connect">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin-bottom:1rem;">
        <div>
          <h2 style="margin:0;">Connect spending source</h2>
          <p style="margin:.25rem 0 0;color:#94a3b8;">
            Link a merchant via Knot so Flux can ingest real transaction data and
            route it through the orchestrator.
          </p>
        </div>
        <div id="knot-health-pill"></div>
      </div>

      <div id="knot-toast" style="display:none;"></div>

      <section id="knot-accounts-section" style="margin-top:1rem;">
        <h3 style="margin:0 0 .5rem;">Linked accounts</h3>
        <div id="knot-accounts"></div>
      </section>

      <section style="margin-top:1.5rem;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem;">
          <h3 style="margin:0;">Available merchants</h3>
          <input
            id="knot-merchant-filter"
            placeholder="Filter merchants…"
            style="background:#0f172a;border:1px solid #1f2937;color:#e2e8f0;padding:.4rem .6rem;border-radius:.4rem;min-width:220px;"
          />
        </div>
        <div id="knot-merchants" style="margin-top:.5rem;"></div>
      </section>

      <div class="charts-grid" style="margin-top:1.5rem;">
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title"><h3>Recent sync runs</h3></div>
            <button class="chart-tab" id="knot-refresh">Refresh</button>
          </div>
          <div class="chart-body" style="padding:.5rem;"><div id="knot-sync-log"></div></div>
        </div>
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title"><h3>Recent webhook events</h3></div>
          </div>
          <div class="chart-body" style="padding:.5rem;"><div id="knot-webhook-events"></div></div>
        </div>
      </div>
    </div>
  `;
}

export async function initConnect() {
  // Load everything in parallel.
  await refreshAll(true);

  document.getElementById('knot-refresh')?.addEventListener('click', () => refreshAll(false));
  document.getElementById('knot-merchant-filter')?.addEventListener('input', (e) => {
    state.filter = (e.target.value || '').toLowerCase();
    renderMerchants();
  });

  // Periodic refresh while on this page so newly arrived webhooks appear.
  if (window.__knotPoller) clearInterval(window.__knotPoller);
  window.__knotPoller = setInterval(() => refreshAll(false), 5000);
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function refreshAll(initial = false) {
  try {
    const [config, health] = await Promise.all([
      safe(fetchKnotConfig),
      safe(fetchKnotHealth),
    ]);
    state.config = config;
    state.health = health;
  } catch (e) { /* ignore */ }

  await Promise.all([
    refreshMerchants(),
    refreshAccounts(),
    refreshSyncLog(),
    refreshWebhooks(),
  ]);

  renderHealthPill();
  renderAccounts();
  renderMerchants();
  renderSyncLog();
  renderWebhooks();
}

async function safe(fn) {
  try { return await fn(); } catch { return null; }
}

async function refreshMerchants() {
  const r = await safe(fetchKnotMerchants);
  state.merchants = (r && r.merchants) || [];
}
async function refreshAccounts() {
  const r = await safe(fetchKnotAccounts);
  state.accounts = (r && r.accounts) || [];
}
async function refreshSyncLog() {
  const r = await safe(() => fetchKnotSyncLog(15));
  state.syncLog = (r && r.log) || [];
}
async function refreshWebhooks() {
  const r = await safe(() => fetchKnotWebhookEvents(15));
  state.webhooks = (r && r.events) || [];
}

// ── Renderers ─────────────────────────────────────────────────────────────────

function renderHealthPill() {
  const el = document.getElementById('knot-health-pill');
  if (!el) return;
  const h = state.health;
  if (!h) {
    el.innerHTML = `<span style="color:#94a3b8;font-size:.85rem;">Knot status: unknown</span>`;
    return;
  }
  const color = h.ok ? '#10b981' : (h.error ? '#ef4444' : '#f59e0b');
  const label = h.ok ? 'connected' : (h.error ? 'error' : 'misconfigured');
  const env = (h.env && h.env.KNOT_ENVIRONMENT) || 'development';
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:.4rem;background:#0f172a;border:1px solid #1f2937;padding:.4rem .6rem;border-radius:.4rem;">
      <span style="display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:${color};"></span>
      <span style="font-size:.85rem;color:#cbd5e1;">Knot ${env} · ${label}</span>
    </div>
  `;
}

function renderAccounts() {
  const el = document.getElementById('knot-accounts');
  if (!el) return;
  if (!state.accounts.length) {
    el.innerHTML = `<div style="color:#94a3b8;background:#0f172a;border:1px dashed #1f2937;padding:1rem;border-radius:.5rem;">No linked accounts yet. Pick a merchant below.</div>`;
    return;
  }
  el.innerHTML = state.accounts.map(a => {
    const status = a.connection_status || 'connected';
    const color = status === 'connected' ? '#10b981' : (status === 'error' ? '#ef4444' : '#f59e0b');
    return `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.75rem;background:#0f172a;border:1px solid #1f2937;border-radius:.5rem;margin-bottom:.5rem;">
        <div>
          <div style="display:flex;align-items:center;gap:.4rem;">
            <span style="display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:${color};"></span>
            <strong>${escapeHtml(a.merchant_name || `Merchant ${a.merchant_id}`)}</strong>
            <span style="color:#64748b;font-size:.8rem;">#${a.merchant_id}</span>
          </div>
          <div style="color:#94a3b8;font-size:.8rem;margin-top:.25rem;">
            status: ${escapeHtml(status)}
            ${a.last_synced_at ? ` · last synced ${new Date(a.last_synced_at).toLocaleString()}` : ''}
            ${a.last_error ? ` · err: ${escapeHtml(a.last_error.slice(0,120))}` : ''}
          </div>
        </div>
        <div style="display:flex;gap:.5rem;">
          <button class="chart-tab" data-action="sync" data-mid="${a.merchant_id}" data-mname="${escapeAttr(a.merchant_name||'')}">${state.busy === `sync:${a.merchant_id}` ? 'Syncing…' : 'Sync now'}</button>
        </div>
      </div>
    `;
  }).join('');
  el.querySelectorAll('button[data-action="sync"]').forEach(btn => {
    btn.addEventListener('click', () => doSync(parseInt(btn.dataset.mid, 10), btn.dataset.mname));
  });
}

function renderMerchants() {
  const el = document.getElementById('knot-merchants');
  if (!el) return;
  const filtered = state.filter
    ? state.merchants.filter(m => (m.name || '').toLowerCase().includes(state.filter))
    : state.merchants;
  if (!filtered.length) {
    el.innerHTML = `<div style="color:#94a3b8;background:#0f172a;border:1px dashed #1f2937;padding:1rem;border-radius:.5rem;">No merchants returned. Check Knot health and credentials.</div>`;
    return;
  }
  const isDev = state.config && state.config.environment === 'development';
  el.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.5rem;">
      ${filtered.slice(0, 60).map(m => `
        <div style="padding:.75rem;background:#0f172a;border:1px solid #1f2937;border-radius:.5rem;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem;">
            <strong style="font-size:.95rem;">${escapeHtml(m.name || 'Merchant')}</strong>
            <span style="color:#64748b;font-size:.75rem;">#${m.id}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:.4rem;margin-top:.5rem;">
            <button class="chart-tab" data-action="connect" data-mid="${m.id}" data-mname="${escapeAttr(m.name||'')}">${state.busy === `connect:${m.id}` ? 'Opening…' : 'Connect via SDK'}</button>
            ${isDev ? `<button class="chart-tab" data-action="simulate" data-mid="${m.id}" data-mname="${escapeAttr(m.name||'')}">${state.busy === `simulate:${m.id}` ? 'Linking…' : 'Simulate link (dev)'}</button>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
  `;
  el.querySelectorAll('button[data-action="connect"]').forEach(btn => {
    btn.addEventListener('click', () => doConnect(parseInt(btn.dataset.mid, 10), btn.dataset.mname));
  });
  el.querySelectorAll('button[data-action="simulate"]').forEach(btn => {
    btn.addEventListener('click', () => doSimulate(parseInt(btn.dataset.mid, 10), btn.dataset.mname));
  });
}

function renderSyncLog() {
  const el = document.getElementById('knot-sync-log');
  if (!el) return;
  if (!state.syncLog.length) {
    el.innerHTML = `<div style="color:#94a3b8;padding:.5rem;">No sync runs yet.</div>`;
    return;
  }
  el.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:.85rem;">
      <thead><tr style="text-align:left;color:#94a3b8;">
        <th style="padding:.4rem;">When</th><th>Merchant</th><th>Trig</th><th>Pages</th><th>Ins</th><th>Upd</th><th>Status</th>
      </tr></thead>
      <tbody>
        ${state.syncLog.map(r => `
          <tr style="border-top:1px solid #1f2937;">
            <td style="padding:.4rem;">${new Date(r.started_at).toLocaleTimeString()}</td>
            <td>#${r.merchant_id}</td>
            <td>${escapeHtml(r.trigger||'')}</td>
            <td>${r.pages_fetched||0}</td>
            <td>${r.inserted_count||0}</td>
            <td>${r.updated_count||0}</td>
            <td style="color:${r.status==='success'?'#10b981':r.status==='error'?'#ef4444':'#f59e0b'};">${escapeHtml(r.status||'')}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderWebhooks() {
  const el = document.getElementById('knot-webhook-events');
  if (!el) return;
  if (!state.webhooks.length) {
    el.innerHTML = `<div style="color:#94a3b8;padding:.5rem;">No webhook events received yet.</div>`;
    return;
  }
  el.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:.85rem;">
      <thead><tr style="text-align:left;color:#94a3b8;">
        <th style="padding:.4rem;">When</th><th>Event</th><th>Merchant</th><th>Status</th>
      </tr></thead>
      <tbody>
        ${state.webhooks.map(r => `
          <tr style="border-top:1px solid #1f2937;">
            <td style="padding:.4rem;">${new Date(r.received_at).toLocaleTimeString()}</td>
            <td>${escapeHtml(r.event||'')}</td>
            <td>${escapeHtml(r.merchant_name||'')} ${r.merchant_id?`#${r.merchant_id}`:''}</td>
            <td style="color:${r.status==='done'?'#10b981':r.status==='error'?'#ef4444':'#f59e0b'};">${escapeHtml(r.status||'')}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function showToast(text, kind = 'info') {
  const el = document.getElementById('knot-toast');
  if (!el) return;
  const color = kind === 'error' ? '#ef4444' : (kind === 'success' ? '#10b981' : '#3b82f6');
  el.style.display = 'block';
  el.style.padding = '.6rem .8rem';
  el.style.borderLeft = `3px solid ${color}`;
  el.style.background = '#0f172a';
  el.style.color = '#e2e8f0';
  el.style.borderRadius = '.4rem';
  el.style.marginTop = '.5rem';
  el.textContent = text;
  clearTimeout(window.__knotToast);
  window.__knotToast = setTimeout(() => { el.style.display = 'none'; }, 5000);
}

// ── Actions ──────────────────────────────────────────────────────────────────

async function doConnect(merchantId, merchantName) {
  state.busy = `connect:${merchantId}`;
  renderMerchants();
  try {
    if (!knotSdkAvailable()) {
      throw new Error('Knot Web SDK not loaded — check that the script is in index.html.');
    }
    const config = state.config || (await fetchKnotConfig());
    if (!config.client_id) {
      throw new Error('KNOT_CLIENT_ID is not configured on the orchestrator.');
    }
    const session = await createKnotSession(config.external_user_id);
    if (!session.session) {
      throw new Error('Orchestrator did not return a session id.');
    }
    openKnotSDK({
      sessionId: session.session,
      clientId: config.client_id,
      environment: config.environment,
      merchantId,
      onSuccess: () => { showToast(`Linked ${merchantName}. Waiting for webhook…`, 'success'); refreshAll(false); },
      onError: (code, msg) => showToast(`Knot SDK error: ${code} ${msg}`, 'error'),
      onExit: () => refreshAll(false),
    });
  } catch (e) {
    showToast(e.message || String(e), 'error');
  } finally {
    state.busy = null;
    renderMerchants();
  }
}

async function doSimulate(merchantId, merchantName) {
  state.busy = `simulate:${merchantId}`;
  renderMerchants();
  try {
    const r = await devSimulateLink({ merchantId, merchantName });
    showToast(`Simulated link for ${merchantName} (#${merchantId}). Webhooks should arrive shortly.`, 'success');
    setTimeout(() => refreshAll(false), 1500);
  } catch (e) {
    const msg = e.detail ? JSON.stringify(e.detail) : (e.message || String(e));
    showToast(`Simulate failed: ${msg}`, 'error');
  } finally {
    state.busy = null;
    renderMerchants();
  }
}

async function doSync(merchantId, merchantName) {
  state.busy = `sync:${merchantId}`;
  renderAccounts();
  try {
    const r = await triggerKnotSync({ merchantId, merchantName, trigger: 'manual' });
    showToast(`Synced #${merchantId}: ${r.inserted||0} new, ${r.updated||0} updated, ${r.pages||0} page(s).`, r.ok===false?'error':'success');
  } catch (e) {
    const msg = e.detail ? JSON.stringify(e.detail) : (e.message || String(e));
    showToast(`Sync failed: ${msg}`, 'error');
  } finally {
    state.busy = null;
    refreshAll(false);
  }
}

// ── Utils ────────────────────────────────────────────────────────────────────

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s).replace(/`/g, ''); }
