// ============================================================
// KNOT — frontend client
//
// All sensitive operations (creds, sessions, sync) live on the
// orchestrator. The browser only:
//   1. asks orchestrator for the public config + a session_id
//   2. opens the Knot Web SDK with that session_id
//   3. asks orchestrator to sync / disconnect
// No Knot secrets ever touch the browser.
// All backend-side activity logs to the orchestrator stdout.
// ============================================================

const ORCHESTRATOR =
  import.meta.env.VITE_ORCHESTRATOR_URL || 'http://localhost:8000';

async function getJSON(path) {
  const r = await fetch(`${ORCHESTRATOR}${path}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

async function postJSON(path, body) {
  const r = await fetch(`${ORCHESTRATOR}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const txt = await r.text();
  let json = {};
  try { json = txt ? JSON.parse(txt) : {}; } catch { json = { raw: txt }; }
  if (!r.ok) throw Object.assign(new Error(`${path} -> ${r.status}`), { detail: json });
  return json;
}

export async function fetchKnotHealth() {
  return getJSON('/knot/health');
}

export async function fetchKnotConfig() {
  return getJSON('/knot/config');
}

export async function fetchKnotMerchants(platform = 'web') {
  return getJSON(`/knot/merchants?platform=${encodeURIComponent(platform)}`);
}

export async function fetchKnotAccounts() {
  return getJSON('/knot/accounts');
}

export async function fetchKnotSyncLog(limit = 25) {
  return getJSON(`/knot/sync/log?limit=${limit}`);
}

export async function fetchKnotWebhookEvents(limit = 25) {
  return getJSON(`/knot/webhook/events?limit=${limit}`);
}

export async function createKnotSession(externalUserId) {
  return postJSON('/knot/session', externalUserId ? { external_user_id: externalUserId } : {});
}

export async function triggerKnotSync({ merchantId, merchantName, externalUserId, trigger = 'manual' }) {
  return postJSON('/knot/sync', {
    merchant_id: merchantId,
    merchant_name: merchantName,
    external_user_id: externalUserId,
    trigger,
  });
}

export async function devSimulateLink({ merchantId, merchantName, externalUserId, newTxns = true, updatedTxns = false }) {
  return postJSON('/knot/dev/simulate-link', {
    merchant_id: merchantId,
    merchant_name: merchantName,
    external_user_id: externalUserId,
    new: newTxns,
    updated: updatedTxns,
  });
}

// ── Web SDK loader ────────────────────────────────────────────
// The script is loaded from the CDN in index.html. This helper
// waits for it and constructs a KnotapiJS instance.

let _knotInstance = null;

export function knotSdkAvailable() {
  return typeof window !== 'undefined' && typeof window.KnotapiJS !== 'undefined';
}

function getKnot() {
  if (_knotInstance) return _knotInstance;
  if (!knotSdkAvailable()) return null;
  const Ctor = window.KnotapiJS.default || window.KnotapiJS;
  _knotInstance = new Ctor();
  return _knotInstance;
}

/**
 * Open the Knot Web SDK for one merchant.
 * @param {object} opts
 * @param {string} opts.sessionId
 * @param {string} opts.clientId
 * @param {string} opts.environment   "development" | "production"
 * @param {number} opts.merchantId
 * @param {string} [opts.entryPoint]
 * @param {function} [opts.onSuccess]
 * @param {function} [opts.onError]
 * @param {function} [opts.onEvent]
 * @param {function} [opts.onExit]
 */
export function openKnotSDK({
  sessionId,
  clientId,
  environment,
  merchantId,
  entryPoint = 'flux-connect',
  onSuccess,
  onError,
  onEvent,
  onExit,
}) {
  const knot = getKnot();
  if (!knot) {
    throw new Error('Knot Web SDK not loaded (knotapi-js script missing)');
  }
  knot.open({
    sessionId,
    clientId,
    environment,
    merchantIds: merchantId ? [merchantId] : undefined,
    entryPoint,
    onSuccess: (details) => onSuccess && onSuccess(details),
    onError: (code, msg) => onError && onError(code, msg),
    onEvent: (event, merchant, mid, payload, taskId) =>
      onEvent && onEvent({ event, merchant, merchantId: mid, payload, taskId }),
    onExit: () => onExit && onExit(),
  });
}
