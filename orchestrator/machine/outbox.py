"""
Machine outbox — sends negotiation emails via SMTP.

In demo mode: logs to console + saves to receipts/ but doesn't send.
In production: sends via Gmail SMTP with retry logic.
"""
from __future__ import annotations

import os
import smtplib
import time
from email.mime.text import MIMEText
from datetime import datetime, timezone
from pathlib import Path

from machine.state import RECEIPTS_DIR, append_log, ensure_dirs


_SMTP_HOST = os.getenv("FLUX_SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("FLUX_SMTP_PORT", "587"))
_EMAIL_ADDR = os.getenv("FLUX_EMAIL_ADDRESS", "")
_EMAIL_PASS = os.getenv("FLUX_EMAIL_APP_PASSWORD", "")
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # seconds, doubles each retry


def _save_receipt(vendor: str, round_num: int, subject: str, body: str, to: str) -> Path:
    """Save a copy of the sent email to the receipts directory."""
    ensure_dirs()
    slug = vendor.lower().replace(" ", "-")
    filename = f"{slug}-round-{round_num}.eml"
    path = RECEIPTS_DIR / filename

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = (
        f"Date: {ts}\n"
        f"To: {to}\n"
        f"From: {_EMAIL_ADDR or 'flux@demo.local'}\n"
        f"Subject: {subject}\n"
        f"\n"
        f"{body}\n"
    )
    path.write_text(content)
    return path


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    vendor: str,
    round_num: int = 0,
    demo: bool = False,
) -> bool:
    """
    Send a negotiation email.

    In demo mode, skips SMTP and just saves the receipt.
    Returns True on success.
    """
    # Always save a receipt
    receipt_path = _save_receipt(vendor, round_num, subject, body, to)

    if demo:
        append_log(vendor, f"DEMO OUTBOX: [round {round_num}] → {to} | Subject: {subject}")
        print(f"  📧 [DEMO] Sent to {to}: {subject}")
        return True

    if not _EMAIL_ADDR or not _EMAIL_PASS:
        append_log(vendor, f"OUTBOX: no SMTP credentials, email saved to {receipt_path}")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = _EMAIL_ADDR
    msg["To"] = to

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
                server.starttls()
                server.login(_EMAIL_ADDR, _EMAIL_PASS)
                server.send_message(msg)

            append_log(vendor, f"OUTBOX: sent round {round_num} to {to} (attempt {attempt})")
            return True

        except Exception as exc:
            append_log(vendor, f"OUTBOX error (attempt {attempt}/{_MAX_RETRIES}): {exc}")
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))

    append_log(vendor, f"OUTBOX: FAILED after {_MAX_RETRIES} retries. Receipt at {receipt_path}")
    return False
