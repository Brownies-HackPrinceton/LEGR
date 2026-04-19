"""
Persistent state management for Dedalus Machines.

All state is stored as JSON files under data/negotiations/.
Writes are atomic (write-to-temp → rename) so a kill mid-write won't corrupt.
Closed deals are archived to data/negotiations/closed/.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Literal, Optional


# ── Directory layout ──────────────────────────────────────────────────────────

_BASE_DIR = Path(os.getenv("MACHINE_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data")))
NEGOTIATIONS_DIR = _BASE_DIR / "negotiations"
CLOSED_DIR = NEGOTIATIONS_DIR / "closed"
LOGS_DIR = _BASE_DIR / "logs"
RECEIPTS_DIR = _BASE_DIR / "receipts"


def ensure_dirs() -> None:
    """Create all data directories if they don't exist."""
    for d in (NEGOTIATIONS_DIR, CLOSED_DIR, LOGS_DIR, RECEIPTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── State dataclass ───────────────────────────────────────────────────────────

NegStatus = Literal[
    "initializing", "email_sent", "waiting_reply",
    "counter_received", "counter_sent",
    "closed_won", "closed_lost", "escalated", "stalled",
]


@dataclass
class ThreadMessage:
    """One message in the negotiation thread."""
    direction: str  # "outbound" | "inbound"
    body: str
    timestamp: str
    round_num: int
    classification: Optional[str] = None  # accept | counter | reject | stall


@dataclass
class NegotiationState:
    """Full state for one negotiation deal."""
    vendor: str
    vendor_email: str
    original_price: float
    target_discount_pct: float
    floor_discount_pct: float = 5.0
    company_id: str = ""
    thread_id: str = ""
    machine_id: str = ""

    status: NegStatus = "initializing"
    current_round: int = 0
    current_offer_pct: Optional[float] = None
    subject_line: str = ""

    thread: List[ThreadMessage] = field(default_factory=list)
    leverage_used: List[str] = field(default_factory=list)
    reasoning_log: List[str] = field(default_factory=list)

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NegotiationState":
        thread_data = data.pop("thread", [])
        threads = [ThreadMessage(**t) if isinstance(t, dict) else t for t in thread_data]
        return cls(**{**data, "thread": threads})


# ── File I/O (atomic) ─────────────────────────────────────────────────────────

def _state_filename(vendor: str) -> str:
    """Normalize vendor name to filesystem-safe slug."""
    slug = vendor.lower().replace(" ", "-").replace("/", "-")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"{slug}-{month}.json"


def state_path(vendor: str) -> Path:
    ensure_dirs()
    return NEGOTIATIONS_DIR / _state_filename(vendor)


def save_state(st: NegotiationState) -> Path:
    """Atomic write: write to temp file then rename."""
    ensure_dirs()
    st.updated_at = datetime.now(timezone.utc).isoformat()
    target = state_path(st.vendor)

    # Write to temp in same directory (same filesystem → rename is atomic)
    fd, tmp_path = tempfile.mkstemp(dir=NEGOTIATIONS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(st.to_dict(), f, indent=2, default=str)
        os.replace(tmp_path, target)
    except Exception:
        # Clean up temp on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target


def load_state(vendor: str) -> Optional[NegotiationState]:
    """Load state from disk. Returns None if not found."""
    p = state_path(vendor)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return NegotiationState.from_dict(data)
    except Exception:
        return None


def archive_state(vendor: str) -> Optional[Path]:
    """Move completed deal to closed/ directory."""
    ensure_dirs()
    src = state_path(vendor)
    if not src.exists():
        return None
    dest = CLOSED_DIR / src.name
    src.rename(dest)
    return dest


# ── Logging ───────────────────────────────────────────────────────────────────

def log_path(vendor: str) -> Path:
    ensure_dirs()
    slug = vendor.lower().replace(" ", "-")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return LOGS_DIR / f"{slug}-{month}.log"


def append_log(vendor: str, message: str) -> None:
    """Append a timestamped line to the vendor's log file."""
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path(vendor), "a") as f:
        f.write(f"[{ts}] {message}\n")


def machine_heartbeat_log(message: str) -> None:
    """Append to the global machine heartbeat log."""
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOGS_DIR / "machine.log", "a") as f:
        f.write(f"[{ts}] {message}\n")
