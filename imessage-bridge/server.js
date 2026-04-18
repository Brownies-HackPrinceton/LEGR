import express from "express";
import { IMessageSDK, asRecipient } from "@photon-ai/imessage-kit";

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3099;
const ORCHESTRATOR_WEBHOOK_URL =
  process.env.ORCHESTRATOR_WEBHOOK_URL || "http://127.0.0.1:8000/webhooks/imessage";
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL_MS || "3000", 10);

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

// Only forward messages that arrive after startup
let lastProcessedAt = new Date();
let dbAvailable = true;

const recentSent = [];
const addToRecent = (text) => {
  recentSent.push(text);
  if (recentSent.length > 50) recentSent.shift();
};

async function pollIncoming() {
  if (!dbAvailable) return;
  try {
    const result = await sdk.getMessages({ limit: 50, excludeOwnMessages: false });
    const messages = Array.isArray(result) ? result : result?.messages || [];

    let latest = lastProcessedAt;
    for (const msg of messages) {
      if (msg.isFromMe) {
        // If the bot sent it, ignore it. If the user typed it from their own device, process it!
        if (recentSent.includes(msg.text)) continue;
      }
      
      const msgDate = msg.date ? new Date(msg.date) : null;
      if (!msgDate || msgDate <= lastProcessedAt) continue;

      await fetch(ORCHESTRATOR_WEBHOOK_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          from_phone: msg.sender || "unknown",
          body: msg.text || "",
          received_at: msg.date,
        }),
      }).catch(() => {});

      if (msgDate > latest) latest = msgDate;
    }
    lastProcessedAt = latest;
  } catch (e) {
    if (String(e).includes("DATABASE") || String(e).includes("database")) {
      dbAvailable = false;
      console.warn("[bridge] DB unavailable, polling stopped. POST /webhooks/incoming for inbound messages.");
    }
  }
}

setInterval(pollIncoming, POLL_INTERVAL_MS);

app.get("/health", (_req, res) => res.json({ status: "ok" }));

function looksLikeE164(value) {
  return typeof value === "string" && /^\+\d{10,15}$/.test(value);
}

// Send plain text
app.post("/send", async (req, res) => {
  const { to, text } = req.body || {};
  if (!to || !text) return res.status(400).json({ error: "missing_to_or_text" });
  if (!looksLikeE164(to))
    return res.status(400).json({ error: "to_must_be_e164", example: "+15551234567" });
  try {
    addToRecent(String(text));
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
  if (!looksLikeE164(to))
    return res.status(400).json({ error: "to_must_be_e164", example: "+15551234567" });
  const opts = Array.isArray(options) && options.length ? options : ["Yes, proceed", "No, skip"];
  try {
    const fullText = `${question}\n\nReply:\nY - ${opts[0]}\nN - ${opts[1]}`;
    addToRecent(fullText);
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
