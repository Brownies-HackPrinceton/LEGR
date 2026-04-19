"""
Canned vendor replies for demo mode.

When the Machine runs with --demo, inbox.py returns these instead of
polling IMAP. Simulates a 3-round negotiation that closes with a win.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List


@dataclass
class FakeEmail:
    from_addr: str
    subject: str
    body: str
    received_at: str


# ── Cursor negotiation scenario ──────────────────────────────────────────────
# Round 1: Vendor acknowledges, offers 10%
# Round 2: Vendor bumps to 18%
# Round 3: Vendor accepts at 22%

CURSOR_REPLIES: List[FakeEmail] = [
    FakeEmail(
        from_addr="renewals@cursor.com",
        subject="Re: Cursor renewal — pricing adjustment",
        body=(
            "Hi there,\n\n"
            "Thanks for reaching out about your renewal. We appreciate your business "
            "and understand the need to optimize costs.\n\n"
            "We can offer a 10% discount on your current plan if you commit to an "
            "annual contract. That would bring your monthly from $480 to $432/mo.\n\n"
            "Let us know if that works.\n\n"
            "Best,\nSarah — Cursor Renewals"
        ),
        received_at=datetime.now(timezone.utc).isoformat(),
    ),
    FakeEmail(
        from_addr="renewals@cursor.com",
        subject="Re: Re: Cursor renewal — pricing adjustment",
        body=(
            "Hi,\n\n"
            "I spoke with my manager and we can go up to 18% off — that's $393.60/mo "
            "on an annual commitment. This is the maximum I'm able to offer at this tier.\n\n"
            "Would that work for your team?\n\n"
            "Best,\nSarah — Cursor Renewals"
        ),
        received_at=datetime.now(timezone.utc).isoformat(),
    ),
    FakeEmail(
        from_addr="renewals@cursor.com",
        subject="Re: Re: Re: Cursor renewal — pricing adjustment",
        body=(
            "Hi,\n\n"
            "After internal review, we've agreed to match your ask. "
            "We can confirm a 22% discount — $374.40/mo on a 12-month term.\n\n"
            "I'll send the updated contract today. Please confirm to proceed.\n\n"
            "Best,\nSarah — Cursor Renewals"
        ),
        received_at=datetime.now(timezone.utc).isoformat(),
    ),
]

# ── Notion negotiation scenario (shorter — vendor declines) ──────────────────

NOTION_REPLIES: List[FakeEmail] = [
    FakeEmail(
        from_addr="billing@makenotion.com",
        subject="Re: Notion team plan — pricing discussion",
        body=(
            "Hi,\n\n"
            "Thank you for being a Notion customer. Unfortunately, we're unable to "
            "offer discounts on the Team plan at this time. Our pricing is standardized "
            "across all customers.\n\n"
            "We'd be happy to help you optimize your seat count instead — we noticed "
            "several inactive members on your workspace.\n\n"
            "Best,\nNotion Support"
        ),
        received_at=datetime.now(timezone.utc).isoformat(),
    ),
]

# ── Generic vendor scenario (accepts at round 2) ────────────────────────────

GENERIC_REPLIES: List[FakeEmail] = [
    FakeEmail(
        from_addr="sales@vendor.com",
        subject="Re: Renewal pricing",
        body=(
            "Hi,\n\n"
            "We can offer 12% off your renewal if you commit to annual billing. "
            "Let me know if you'd like to proceed.\n\n"
            "Regards,\nVendor Sales"
        ),
        received_at=datetime.now(timezone.utc).isoformat(),
    ),
    FakeEmail(
        from_addr="sales@vendor.com",
        subject="Re: Re: Renewal pricing",
        body=(
            "Hi,\n\n"
            "We've agreed to your requested 20% discount. Confirmed and applied "
            "to your next billing cycle.\n\n"
            "Regards,\nVendor Sales"
        ),
        received_at=datetime.now(timezone.utc).isoformat(),
    ),
]


def get_demo_replies(vendor: str) -> List[FakeEmail]:
    """Return the canned reply sequence for a vendor."""
    v = vendor.lower().strip()
    if "cursor" in v:
        return CURSOR_REPLIES
    elif "notion" in v:
        return NOTION_REPLIES
    else:
        return GENERIC_REPLIES
