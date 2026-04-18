import express from "express";
import { IMessageSDK, asRecipient } from "@photon-ai/imessage-kit";

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3099;
const ORCHESTRATOR_WEBHOOK_URL =
  process.env.ORCHESTRATOR_WEBHOOK_URL || "http://127.0.0.1:8000/webhooks/imessage";
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL_MS || "5000", 10);

// Suppress SDK init noise then restore
const _log = console.log;
const _info = console.info;
console.log = () => {};
console.info = () => {};
const sdk = new IMessageSDK({ debug: false, maxConcurrent: 5 });
console.log = _log;
console.info = _info;

// Absorb the DB initPromise rejection so Node doesn't crash when Full Disk
// Access hasn't been granted yet (send still works via AppleScript).
process.on("unhandledRejection", (reason) => {
  if (String(reason).includes("Failed to open database")) {
    console.warn("[bridge] No Full Disk Access — incoming message polling disabled. Grant FDA to Terminal/VS Code in System Settings → Privacy & Security.");
  } else {
    console.error("[bridge] Unhandled rejection:", reason);
  }
});

let dbAvailable = true;
let polling = false;

// ID-based deduplication: any message seen before startup (or already forwarded)
// will be in this set and silently skipped.
const seenMessageIds = new Set();

async function initializeSeenIds() {
  if (!dbAvailable) return;
  try {
    const result = await sdk.getMessages({ limit: 500, excludeOwnMessages: false });
    const messages = Array.isArray(result) ? result : result?.messages || [];
    for (const msg of messages) {
      if (msg.id) seenMessageIds.add(msg.id);
    }
    console.log(`[bridge] Seeded ${seenMessageIds.size} existing message IDs — only new messages will be forwarded.`);
  } catch (e) {
    if (String(e).includes("DATABASE") || String(e).includes("database")) {
      dbAvailable = false;
      console.warn("[bridge] DB unavailable during init, polling disabled.");
    } else {
      console.warn("[bridge] Could not seed message IDs:", e.message);
    }
  }
}

async function pollIncoming() {
  if (!dbAvailable || polling) return;
  polling = true;
  try {
    const result = await sdk.getMessages({ limit: 50, excludeOwnMessages: false });
    const messages = Array.isArray(result) ? result : result?.messages || [];

    for (const msg of messages) {
      // Never process messages sent by this machine (bot replies, user typing from Mac)
      if (msg.isFromMe) continue;

      // Skip anything we've already seen
      if (!msg.id || seenMessageIds.has(msg.id)) continue;

      seenMessageIds.add(msg.id);

      await fetch(ORCHESTRATOR_WEBHOOK_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          from_phone: msg.sender || "unknown",
          body: msg.text || "",
          received_at: msg.date,
        }),
      }).catch((err) => console.warn("[bridge] Orchestrator unreachable:", err.message));

      console.log(`[bridge] Forwarded msg ${msg.id} from ${msg.sender}`);
    }
  } catch (e) {
    if (String(e).includes("DATABASE") || String(e).includes("database")) {
      dbAvailable = false;
      console.warn("[bridge] DB unavailable, polling stopped. POST /webhooks/incoming for inbound messages.");
    }
  } finally {
    polling = false;
  }
}

// Seed on startup, then begin polling
initializeSeenIds().then(() => {
  setInterval(pollIncoming, POLL_INTERVAL_MS);
});

app.get("/health", (_req, res) => res.json({ status: "ok", seenIds: seenMessageIds.size, dbAvailable }));

function isValidRecipient(value) {
  if (typeof value !== "string") return false;
  const isE164 = /^\+\d{10,15}$/.test(value);
  const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  return isE164 || isEmail;
}

// Send plain text
app.post("/send", async (req, res) => {
  const { to, text } = req.body || {};
  if (!to || !text) return res.status(400).json({ error: "missing_to_or_text" });
  if (!isValidRecipient(to))
    return res.status(400).json({ error: "invalid_recipient", example: "+15551234567 or email@icloud.com" });
  try {
    await sdk.send(asRecipient(to), String(text));
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

// Send a Y/N poll (emulated via text)
app.post("/send_poll", async (req, res) => {
  const { to, question, options } = req.body || {};
  if (!to || !question) return res.status(400).json({ error: "missing_to_or_question" });
  if (!isValidRecipient(to))
    return res.status(400).json({ error: "invalid_recipient", example: "+15551234567 or email@icloud.com" });
  const opts = Array.isArray(options) && options.length ? options : ["Yes, proceed", "No, skip"];
  try {
    const fullText = `${question}\n\nReply:\nY - ${opts[0]}\nN - ${opts[1]}`;
    await sdk.send(asRecipient(to), fullText);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

// Photon webhook push (backup path) → forward to orchestrator
app.post("/webhooks/incoming", async (req, res) => {
  const payload = req.body || {};
  try {
    const r = await fetch(ORCHESTRATOR_WEBHOOK_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await r.text();
    res.status(200).send(text);
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

app.listen(PORT, () => {
  console.log(`iMessage bridge listening on http://127.0.0.1:${PORT}`);
});
