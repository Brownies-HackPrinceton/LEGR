"use client";

import { useCallback, useEffect, useState } from "react";
import {
  KnotAccount,
  KnotConfig,
  KnotHealth,
  KnotMerchant,
  KnotSyncLogEntry,
  KnotWebhookEventRow,
  createKnotSession,
  devSimulateLink,
  fetchKnotAccounts,
  fetchKnotConfig,
  fetchKnotHealth,
  fetchKnotMerchants,
  fetchKnotSyncLog,
  fetchKnotWebhookEvents,
  openKnotSDK,
  triggerKnotSync,
  unwrapList,
} from "@/lib/knot";
import { useToast } from "@/components/Toast";

const REFRESH_MS = 10_000;

type Busy = Record<number, boolean>;

export function ConnectClient() {
  const toast = useToast();

  const [health, setHealth] = useState<KnotHealth | null>(null);
  const [config, setConfig] = useState<KnotConfig | null>(null);
  const [merchants, setMerchants] = useState<KnotMerchant[]>([]);
  const [accounts, setAccounts] = useState<KnotAccount[]>([]);
  const [syncLog, setSyncLog] = useState<KnotSyncLogEntry[]>([]);
  const [webhooks, setWebhooks] = useState<KnotWebhookEventRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>({});

  const refresh = useCallback(async () => {
    try {
      const [h, c, m, a, s, w] = await Promise.allSettled([
        fetchKnotHealth(),
        fetchKnotConfig(),
        fetchKnotMerchants("web"),
        fetchKnotAccounts(),
        fetchKnotSyncLog(25),
        fetchKnotWebhookEvents(25),
      ]);
      if (h.status === "fulfilled") setHealth(h.value);
      if (c.status === "fulfilled") setConfig(c.value);
      if (m.status === "fulfilled") {
        setMerchants(unwrapList<"merchants", KnotMerchant>(m.value, "merchants"));
      }
      if (a.status === "fulfilled") {
        setAccounts(unwrapList<"accounts", KnotAccount>(a.value, "accounts"));
      }
      if (s.status === "fulfilled") {
        setSyncLog(unwrapList<"log", KnotSyncLogEntry>(s.value, "log"));
      }
      if (w.status === "fulfilled") {
        setWebhooks(
          unwrapList<"events", KnotWebhookEventRow>(w.value, "events"),
        );
      }
      const failures = [h, c, m, a, s, w].filter((r) => r.status === "rejected");
      if (failures.length === 6) {
        setLoadError(
          "Could not reach the orchestrator. Is it running on " +
            (process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ??
              "http://localhost:8000") +
            "?",
        );
      } else {
        setLoadError(null);
      }
    } catch (e) {
      setLoadError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const setBusyFor = (id: number, v: boolean) =>
    setBusy((prev) => ({ ...prev, [id]: v }));

  const handleConnect = async (m: KnotMerchant) => {
    if (!config) {
      toast.push("err", "Knot config not loaded yet");
      return;
    }
    setBusyFor(m.id, true);
    try {
      const session = await createKnotSession(config.external_user_id);
      toast.push("info", `Session created for ${m.name}`);
      await openKnotSDK({
        sessionId: session.session,
        clientId: config.client_id,
        environment: config.environment,
        merchantId: m.id,
        onSuccess: async () => {
          toast.push("ok", `${m.name} linked. Syncing…`);
          try {
            const r = await triggerKnotSync({
              merchantId: m.id,
              merchantName: m.name,
              externalUserId: config.external_user_id,
              trigger: "post-link",
            });
            toast.push(
              "ok",
              `${m.name}: +${r.inserted} new, ${r.updated} updated`,
            );
          } catch (err) {
            toast.push("err", `${m.name} sync failed: ${(err as Error).message}`);
          }
          refresh();
        },
        onError: (e) => {
          toast.push(
            "err",
            `${m.name} SDK error: ${e.errorCode} ${e.errorDescription}`,
          );
        },
        onExit: () => refresh(),
      });
    } catch (e) {
      toast.push("err", `Connect failed: ${(e as Error).message}`);
    } finally {
      setBusyFor(m.id, false);
    }
  };

  const handleSync = async (m: KnotMerchant) => {
    setBusyFor(m.id, true);
    try {
      const r = await triggerKnotSync({
        merchantId: m.id,
        merchantName: m.name,
        externalUserId: config?.external_user_id,
        trigger: "manual",
      });
      toast.push("ok", `${m.name}: +${r.inserted} new, ${r.updated} updated`);
      refresh();
    } catch (e) {
      toast.push("err", `${m.name} sync failed: ${(e as Error).message}`);
    } finally {
      setBusyFor(m.id, false);
    }
  };

  const handleSimulate = async (m: KnotMerchant) => {
    setBusyFor(m.id, true);
    try {
      await devSimulateLink({
        merchantId: m.id,
        merchantName: m.name,
        externalUserId: config?.external_user_id,
      });
      toast.push("ok", `Simulated link for ${m.name}`);
      refresh();
    } catch (e) {
      toast.push("err", `Simulate failed: ${(e as Error).message}`);
    } finally {
      setBusyFor(m.id, false);
    }
  };

  const isProd = config?.environment === "production";

  return (
    <>
      <div className="panel">
        <h2>Knot status</h2>
        <div className="row">
          <HealthPill health={health} />
          {config && (
            <>
              <span className="pill mono">
                user: {config.external_user_id}
              </span>
            </>
          )}
          {health?.env?.KNOT_VERIFY_WEBHOOKS ? (
            <span className="pill ok">webhook signatures: on</span>
          ) : (
            <span className="pill warn">webhook signatures: off</span>
          )}
          {health?.env?.KNOT_PUBLIC_WEBHOOK_URL && (
            <span className="pill mono" title={health.env.KNOT_PUBLIC_WEBHOOK_URL}>
              webhook url: set
            </span>
          )}
          {health?.env && health.env.SUPABASE_URL_present === false && (
            <span className="pill warn">supabase: not configured</span>
          )}
        </div>
        {loadError && <p className="err-text" style={{ marginTop: 12 }}>{loadError}</p>}
      </div>

      <div className="panel">
        <h2>Linked accounts ({accounts.length})</h2>
        {accounts.length === 0 ? (
          <p className="muted">No accounts linked yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Status</th>
                <th>Last sync</th>
                <th>Last error</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}>
                  <td>{a.merchant_name ?? `#${a.merchant_id}`}</td>
                  <td>
                    <span className={`pill ${a.connection_status === "connected" ? "ok" : "warn"}`}>
                      {a.connection_status}
                    </span>
                  </td>
                  <td className="mono">{a.last_synced_at ?? "—"}</td>
                  <td className="err-text mono">{a.last_error ?? ""}</td>
                  <td>
                    <button
                      className="ghost"
                      disabled={busy[a.merchant_id]}
                      onClick={() =>
                        handleSync({
                          id: a.merchant_id,
                          name: a.merchant_name ?? `#${a.merchant_id}`,
                        })
                      }
                    >
                      {busy[a.merchant_id] ? "Syncing…" : "Sync now"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h2>Available merchants ({merchants.length})</h2>
        {merchants.length === 0 ? (
          <p className="muted">No merchants returned.</p>
        ) : (
          <div className="merchant-grid">
            {merchants.map((m) => (
              <div key={m.id} className="merchant-card">
                <div className="name">{m.name}</div>
                <div className="meta">
                  id: {m.id}
                  {m.category ? ` · ${m.category}` : ""}
                </div>
                <div className="actions">
                  <button
                    disabled={busy[m.id]}
                    onClick={() => handleConnect(m)}
                  >
                    {busy[m.id] ? "Working…" : "Connect via SDK"}
                  </button>
                  {!isProd && (
                    <button
                      className="ghost"
                      disabled={busy[m.id]}
                      onClick={() => handleSimulate(m)}
                      title="Dev only: pretend a user just linked this merchant"
                    >
                      Simulate
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Recent sync runs</h2>
        {syncLog.length === 0 ? (
          <p className="muted">No sync runs yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Merchant</th>
                <th>Trigger</th>
                <th>Inserted</th>
                <th>Updated</th>
                <th>Status</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {syncLog.map((s) => (
                <tr key={s.id}>
                  <td className="mono">{s.started_at}</td>
                  <td>{s.merchant_id}</td>
                  <td>{s.trigger}</td>
                  <td>{s.inserted_count}</td>
                  <td>{s.updated_count}</td>
                  <td>
                    <span
                      className={`pill ${
                        s.status === "ok"
                          ? "ok"
                          : s.status === "running"
                            ? "info"
                            : "err"
                      }`}
                    >
                      {s.status}
                    </span>
                  </td>
                  <td className="err-text mono">{s.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h2>Recent webhooks</h2>
        {webhooks.length === 0 ? (
          <p className="muted">
            No webhook events recorded. Confirm <code>KNOT_PUBLIC_WEBHOOK_URL</code>{" "}
            is reachable from the public internet (e.g. via ngrok / cloudflared).
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Received</th>
                <th>Event</th>
                <th>Merchant</th>
                <th>Status</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {webhooks.map((w) => (
                <tr key={w.id}>
                  <td className="mono">{w.received_at}</td>
                  <td>{w.event}</td>
                  <td>{w.merchant_name ?? w.merchant_id ?? "—"}</td>
                  <td>
                    <span
                      className={`pill ${
                        w.status === "processed"
                          ? "ok"
                          : w.status === "received"
                            ? "info"
                            : "err"
                      }`}
                    >
                      {w.status}
                    </span>
                  </td>
                  <td className="err-text mono">{w.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function HealthPill({ health }: { health: KnotHealth | null }) {
  if (!health) return <span className="pill">checking…</span>;
  if (health.ok) {
    const env = health.env?.KNOT_ENVIRONMENT ?? "?";
    return (
      <span className="pill ok">
        Knot · {env} · connected
      </span>
    );
  }
  return (
    <span className="pill err">
      Knot · unreachable{health.error ? ` (${health.error})` : ""}
    </span>
  );
}
