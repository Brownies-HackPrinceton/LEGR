// ============================================================
// KNOT — frontend client (Next.js)
//
// All sensitive operations (creds, sessions, sync) live on the
// orchestrator. The browser only:
//   1. asks orchestrator for the public config + a session_id
//   2. opens the Knot Web SDK with that session_id
//   3. asks orchestrator to sync / disconnect
//
// No Knot secrets ever touch the browser. All backend-side
// activity logs to the orchestrator stdout (see
// orchestrator/integrations/knot/log.py).
// ============================================================

const ORCHESTRATOR =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || "http://localhost:8000";

// ── HTTP helpers ─────────────────────────────────────────────

async function getJSON<T = unknown>(path: string): Promise<T> {
  const r = await fetch(`${ORCHESTRATOR}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

async function postJSON<T = unknown>(
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const r = await fetch(`${ORCHESTRATOR}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
    cache: "no-store",
  });
  const txt = await r.text();
  let json: unknown = {};
  try {
    json = txt ? JSON.parse(txt) : {};
  } catch {
    json = { raw: txt };
  }
  if (!r.ok) {
    const err = new Error(`${path} -> ${r.status}`) as Error & {
      detail?: unknown;
      status?: number;
    };
    err.detail = json;
    err.status = r.status;
    throw err;
  }
  return json as T;
}

// ── Types ────────────────────────────────────────────────────

// /knot/health returns ``{ok, env: {KNOT_ENVIRONMENT, KNOT_VERIFY_WEBHOOKS, ...}, error}``
export type KnotHealth = {
  ok: boolean;
  env?: {
    KNOT_ENVIRONMENT?: string;
    KNOT_CLIENT_ID_present?: boolean;
    KNOT_SECRET_present?: boolean;
    KNOT_VERIFY_WEBHOOKS?: boolean;
    KNOT_PUBLIC_WEBHOOK_URL?: string;
    SUPABASE_URL_present?: boolean;
    SUPABASE_SERVICE_KEY_present?: boolean;
  };
  error?: string | null;
};

// /knot/config returns ``{client_id, environment, external_user_id, company_id}``
export type KnotConfig = {
  client_id: string;
  environment: "development" | "production" | string;
  external_user_id: string;
  company_id?: string;
};

export type KnotMerchant = {
  id: number;
  name: string;
  logo_url?: string | null;
  category?: string | null;
  type?: string;
};

export type KnotAccount = {
  id: string;
  external_user_id: string;
  merchant_id: number;
  merchant_name?: string | null;
  connection_status: string;
  last_authenticated_at?: string | null;
  last_synced_at?: string | null;
  last_error?: string | null;
};

export type KnotSyncLogEntry = {
  id: string;
  external_user_id: string;
  merchant_id: number;
  trigger: string;
  inserted_count: number;
  updated_count: number;
  status: string;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
  error?: string | null;
};

export type KnotWebhookEventRow = {
  id: string;
  event: string;
  external_user_id?: string | null;
  merchant_id?: number | null;
  merchant_name?: string | null;
  status: string;
  received_at: string;
  processed_at?: string | null;
  error?: string | null;
};

// ── REST wrappers ────────────────────────────────────────────

export function fetchKnotHealth() {
  return getJSON<KnotHealth>("/knot/health");
}

export function fetchKnotConfig() {
  return getJSON<KnotConfig>("/knot/config");
}

export function fetchKnotMerchants(platform: string = "web") {
  return getJSON<{ merchants: KnotMerchant[] } | KnotMerchant[]>(
    `/knot/merchants?platform=${encodeURIComponent(platform)}`,
  );
}

export function fetchKnotAccounts() {
  return getJSON<{ accounts: KnotAccount[] } | KnotAccount[]>(
    "/knot/accounts",
  );
}

export function fetchKnotSyncLog(limit = 25) {
  // Backend wraps the rows under ``log`` (alongside ``company_id``).
  return getJSON<{ log: KnotSyncLogEntry[] } | KnotSyncLogEntry[]>(
    `/knot/sync/log?limit=${limit}`,
  );
}

export function fetchKnotWebhookEvents(limit = 25) {
  return getJSON<{ events: KnotWebhookEventRow[] } | KnotWebhookEventRow[]>(
    `/knot/webhook/events?limit=${limit}`,
  );
}

export function createKnotSession(externalUserId?: string) {
  return postJSON<{ session: string; external_user_id?: string }>(
    "/knot/session",
    externalUserId ? { external_user_id: externalUserId } : undefined,
  );
}

export function triggerKnotSync(opts: {
  merchantId: number;
  merchantName?: string;
  externalUserId?: string;
  trigger?: string;
}) {
  return postJSON<{
    inserted: number;
    updated: number;
    status: string;
    duration_ms?: number;
  }>("/knot/sync", {
    merchant_id: opts.merchantId,
    merchant_name: opts.merchantName,
    external_user_id: opts.externalUserId,
    trigger: opts.trigger ?? "manual",
  });
}

export function devSimulateLink(opts: {
  merchantId: number;
  merchantName?: string;
  externalUserId?: string;
  newTxns?: boolean;
  updatedTxns?: boolean;
}) {
  return postJSON<unknown>("/knot/dev/simulate-link", {
    merchant_id: opts.merchantId,
    merchant_name: opts.merchantName,
    external_user_id: opts.externalUserId,
    new: opts.newTxns ?? true,
    updated: opts.updatedTxns ?? false,
  });
}

// ── Web SDK ──────────────────────────────────────────────────
// We import lazily on the client to avoid pulling the SDK into
// the server bundle.

import type { KnotError, KnotEvent, KnotExit, KnotSuccess } from "knotapi-js";

type SdkEnvironment = "production" | "sandbox" | "development";

type OpenOpts = {
  sessionId: string;
  clientId: string;
  environment: string;
  merchantId: number;
  entryPoint?: string;
  onSuccess?: (s: KnotSuccess) => void;
  onError?: (e: KnotError) => void;
  onEvent?: (e: KnotEvent) => void;
  onExit?: (x: KnotExit) => void;
};

type KnotInstance = { open: (config: Record<string, unknown>) => void };

let _knotInstance: KnotInstance | null = null;

async function getKnot(): Promise<KnotInstance | null> {
  if (_knotInstance) return _knotInstance;
  if (typeof window === "undefined") return null;
  const mod = await import("knotapi-js");
  const Ctor = mod.default;
  _knotInstance = new Ctor() as unknown as KnotInstance;
  return _knotInstance;
}

function asSdkEnvironment(env: string): SdkEnvironment {
  if (env === "production" || env === "sandbox" || env === "development") {
    return env;
  }
  // Knot's API uses `development` / `production`; map anything else safely.
  return "development";
}

export async function openKnotSDK(opts: OpenOpts): Promise<void> {
  const knot = await getKnot();
  if (!knot) throw new Error("Knot Web SDK unavailable in this environment");
  knot.open({
    sessionId: opts.sessionId,
    clientId: opts.clientId,
    environment: asSdkEnvironment(opts.environment),
    merchantIds: opts.merchantId ? [opts.merchantId] : undefined,
    entryPoint: opts.entryPoint ?? "flux-connect",
    onSuccess: opts.onSuccess,
    onError: opts.onError,
    onEvent: opts.onEvent,
    onExit: opts.onExit,
  });
}

// ── Helpers ──────────────────────────────────────────────────

export function unwrapList<K extends string, T>(
  data: { [P in K]: T[] } | T[] | null | undefined,
  key: K,
): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  const v = (data as Record<string, unknown>)[key];
  return Array.isArray(v) ? (v as T[]) : [];
}
