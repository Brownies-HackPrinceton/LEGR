"""
Machine inbox — polls for vendor email replies.

In production mode: connects to IMAP, fetches new mail matching the
negotiation subject line, parses body, closes connection.

In demo mode: returns the next canned reply from demo_fixtures.py.
"""
from __future__ import annotations

import email
import imaplib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from machine.demo_fixtures import FakeEmail, get_demo_replies
from machine.state import append_log


@dataclass
class IncomingEmail:
    """Parsed inbound email from a vendor."""
    from_addr: str
    subject: str
    body: str
    received_at: str


class DemoInbox:
    """Yields one canned reply per poll call, simulating real email."""

    def __init__(self, vendor: str):
        self._replies = get_demo_replies(vendor)
        self._index = 0

    def poll(self, vendor: str, subject_filter: str = "") -> List[IncomingEmail]:
        if self._index >= len(self._replies):
            return []
        reply: FakeEmail = self._replies[self._index]
        self._index += 1
        return [
            IncomingEmail(
                from_addr=reply.from_addr,
                subject=reply.subject,
                body=reply.body,
                received_at=reply.received_at,
            )
        ]


class IMAPInbox:
    """Real IMAP polling for vendor replies."""

    def __init__(self):
        self._host = os.getenv("FLUX_IMAP_HOST", "imap.gmail.com")
        self._port = int(os.getenv("FLUX_IMAP_PORT", "993"))
        self._user = os.getenv("FLUX_EMAIL_ADDRESS", "")
        self._password = os.getenv("FLUX_EMAIL_APP_PASSWORD", "")

    def poll(self, vendor: str, subject_filter: str = "") -> List[IncomingEmail]:
        if not self._user or not self._password:
            append_log(vendor, "IMAP: no credentials configured, skipping poll")
            return []

        results: List[IncomingEmail] = []
        conn: Optional[imaplib.IMAP4_SSL] = None

        try:
            conn = imaplib.IMAP4_SSL(self._host, self._port)
            conn.login(self._user, self._password)
            conn.select("INBOX")

            # Search for emails matching the subject
            search_criteria = f'(UNSEEN SUBJECT "{subject_filter}")' if subject_filter else "(UNSEEN)"
            _, msg_ids = conn.search(None, search_criteria)

            for msg_id in (msg_ids[0] or b"").split():
                _, msg_data = conn.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                parsed = email.message_from_bytes(raw_email)

                body = ""
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                            break
                else:
                    payload = parsed.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                results.append(
                    IncomingEmail(
                        from_addr=parsed.get("From", ""),
                        subject=parsed.get("Subject", ""),
                        body=body,
                        received_at=datetime.now(timezone.utc).isoformat(),
                    )
                )

                # Mark as seen
                conn.store(msg_id, "+FLAGS", "\\Seen")

            append_log(vendor, f"IMAP: polled, found {len(results)} new emails")

        except Exception as exc:
            append_log(vendor, f"IMAP error: {exc}")
        finally:
            if conn:
                try:
                    conn.logout()
                except Exception:
                    pass

        return results


def create_inbox(demo: bool = False, vendor: str = "") -> DemoInbox | IMAPInbox:
    """Factory: return demo or real inbox based on mode."""
    if demo:
        return DemoInbox(vendor)
    return IMAPInbox()
