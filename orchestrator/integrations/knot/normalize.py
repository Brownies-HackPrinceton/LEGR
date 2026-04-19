"""
Normalize Knot transaction objects into rows for the existing
`transactions` table.

Knot transaction object:
    id, external_id, datetime, order_status, url,
    price{ sub_total, total, currency, adjustments[] },
    products[], payment_methods[], shipping{}

Flux transactions row (extended):
    id (db gen), company_id, merchant, amount, category,
    submitted_by, employee_id (null for Knot), memo,
    status, pillar, agent_assigned, agent_reasoning, agent_output,
    founder_action, savings_identified,
    -- new from migration 007 --
    provider, external_id, external_user_id, merchant_id, merchant_name,
    order_status, currency, occurred_at, order_url,
    payment_methods, products, shipping, raw_payload

Mapping rules:
  - provider           = 'knot'
  - external_id        = txn["id"]
  - merchant fields    = from sync wrapper
  - amount             = price.total (numeric)
  - merchant           = merchant_name (back-compat for agents that read .merchant)
  - submitted_by       = "knot"
  - memo               = best-effort first product name
  - status             = 'pending' (existing default semantics)
  - All other Flux fields stay default; agents fill them in later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _safe_float(v: Any) -> float:
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _parse_iso(v: Any) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, str):
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception:
            return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            return None
    return None


def _first_product_name(products: Any) -> Optional[str]:
    if not isinstance(products, list) or not products:
        return None
    first = products[0]
    if isinstance(first, dict):
        name = first.get("name")
        return str(name) if name else None
    return None


def knot_to_transaction_row(
    txn: dict[str, Any],
    *,
    company_id: str,
    external_user_id: str,
    merchant_id: int,
    merchant_name: str,
) -> dict[str, Any]:
    """
    Convert a single Knot transaction object into a `transactions` row dict
    suitable for upsert.
    """
    if not isinstance(txn, dict) or not txn.get("id"):
        raise ValueError("knot transaction missing id")

    price = txn.get("price") or {}
    amount = _safe_float(price.get("total"))
    currency = price.get("currency")

    products = txn.get("products") or []
    payment_methods = txn.get("payment_methods") or []
    shipping = txn.get("shipping")

    occurred_at = _parse_iso(txn.get("datetime"))
    memo = _first_product_name(products) or txn.get("external_id") or ""

    return {
        # Existing schema
        "company_id": company_id,
        "merchant": str(merchant_name)[:255] if merchant_name else None,
        "amount": amount,
        "category": None,                  # let agents/orchestrator classify
        "submitted_by": "knot",
        "employee_id": None,
        "memo": str(memo)[:500] if memo else None,
        "status": "pending",
        # 007 additions
        "provider": "knot",
        "external_id": str(txn["id"]),
        "external_user_id": external_user_id,
        "merchant_id": int(merchant_id),
        "merchant_name": str(merchant_name) if merchant_name else None,
        "order_status": txn.get("order_status"),
        "currency": currency,
        "occurred_at": occurred_at,
        "order_url": txn.get("url"),
        "payment_methods": payment_methods,
        "products": products,
        "shipping": shipping,
        "raw_payload": txn,
    }
