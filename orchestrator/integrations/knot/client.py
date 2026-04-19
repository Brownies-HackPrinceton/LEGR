"""
Typed Knot HTTP client.

- Basic Auth: Authorization: Basic base64(client_id:secret)
- Two base URLs: development, production
- Methods cover the surface we actually use:
    * list_merchants(platform, type)
    * create_session(external_user_id, type)
    * sync_transactions(external_user_id, merchant_id, cursor, limit)
    * get_transaction(transaction_id)
    * get_accounts(external_user_id)
    * dev_simulate_link(external_user_id, merchant_id, new, updated)
- All errors raise KnotAPIError with status + body so the caller can
  log + persist.

Credentials come from env vars only; never hardcoded.
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Literal, Optional

import httpx

from . import log

KnotEnv = Literal["development", "production"]

_PROD_URL = "https://production.knotapi.com"
_DEV_URL = "https://development.knotapi.com"


class KnotConfigError(RuntimeError):
    """Raised when required Knot env vars are missing."""


class KnotAPIError(RuntimeError):
    """Raised when Knot returns a non-2xx response."""

    def __init__(self, status: int, body: Any, *, url: str, method: str):
        super().__init__(f"Knot {method} {url} -> {status}: {body}")
        self.status = status
        self.body = body
        self.url = url
        self.method = method


def _resolve_environment() -> KnotEnv:
    raw = (os.getenv("KNOT_ENVIRONMENT") or "development").strip().lower()
    if raw not in ("development", "production"):
        raise KnotConfigError(f"KNOT_ENVIRONMENT must be development|production, got {raw!r}")
    return raw  # type: ignore[return-value]


def _resolve_base_url(env: KnotEnv) -> str:
    override = (os.getenv("KNOT_BASE_URL") or "").strip()
    if override:
        return override.rstrip("/")
    return _PROD_URL if env == "production" else _DEV_URL


def _resolve_auth_header() -> str:
    client_id = (os.getenv("KNOT_CLIENT_ID") or "").strip()
    secret = (os.getenv("KNOT_SECRET") or "").strip()
    if not client_id or not secret:
        raise KnotConfigError(
            "Missing KNOT_CLIENT_ID or KNOT_SECRET. Get them from "
            "https://dashboard.knotapi.com/developers/keys (development env)."
        )
    token = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


class KnotClient:
    """Thin async wrapper over Knot's REST API."""

    def __init__(
        self,
        *,
        environment: Optional[KnotEnv] = None,
        base_url: Optional[str] = None,
        auth_header: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.environment: KnotEnv = environment or _resolve_environment()
        self.base_url = (base_url or _resolve_base_url(self.environment)).rstrip("/")
        self._auth = auth_header or _resolve_auth_header()
        self._timeout = timeout

    # ── Internal request helper ──────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "flux-knot/1.0",
        }
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    r = await c.request(
                        method, url, headers=headers, json=json_body, params=params
                    )
                if r.status_code == 429 and attempt < max_retries:
                    sleep = 2 ** attempt
                    log.warn("rate_limited", url=url, attempt=attempt, sleep=sleep)
                    await asyncio.sleep(sleep)
                    continue
                if r.status_code >= 500 and attempt < max_retries:
                    sleep = 2 ** attempt
                    log.warn(
                        "knot_5xx_retry", url=url, status=r.status_code, attempt=attempt, sleep=sleep
                    )
                    await asyncio.sleep(sleep)
                    continue
                if r.status_code >= 400:
                    body: Any
                    try:
                        body = r.json()
                    except Exception:
                        body = r.text
                    raise KnotAPIError(r.status_code, body, url=url, method=method)
                if not r.content:
                    return {}
                return r.json()
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < max_retries:
                    sleep = 2 ** attempt
                    log.warn(
                        "knot_network_retry",
                        url=url,
                        err=str(exc),
                        attempt=attempt,
                        sleep=sleep,
                    )
                    await asyncio.sleep(sleep)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    # ── Public API ───────────────────────────────────────────────────────

    async def list_merchants(
        self,
        *,
        type: str = "transaction_link",
        platform: str = "web",
        search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """POST /merchant/list — per https://docs.knotapi.com/api-reference/merchants/list-merchants."""
        body: dict[str, Any] = {"type": type}
        if platform:
            body["platform"] = platform
        if search:
            body["search"] = search
        log.info("api.list_merchants", type=type, platform=platform, search=search)
        data = await self._request("POST", "/merchant/list", json_body=body)
        if isinstance(data, dict) and "merchants" in data:
            return list(data["merchants"] or [])
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "id" in data and "name" in data:
            return [data]
        return []

    async def create_session(
        self,
        *,
        external_user_id: str,
        type: str = "transaction_link",
        metadata: Optional[dict[str, str]] = None,
        email: Optional[str] = None,
        phone_number: Optional[str] = None,
    ) -> dict[str, Any]:
        """POST /session/create — returns ``{"session": "<id>"}`` on success."""
        body: dict[str, Any] = {"type": type, "external_user_id": external_user_id}
        if metadata:
            body["metadata"] = {str(k): str(v) for k, v in metadata.items()}
        if email:
            body["email"] = email
        if phone_number:
            body["phone_number"] = phone_number
        log.info("api.create_session", external_user_id=external_user_id, type=type,
                 has_metadata=bool(metadata))
        data = await self._request("POST", "/session/create", json_body=body)
        return data if isinstance(data, dict) else {}

    async def sync_transactions(
        self,
        *,
        external_user_id: str,
        merchant_id: int,
        cursor: Optional[str],
        limit: int = 50,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "external_user_id": external_user_id,
            "merchant_id": int(merchant_id),
            "limit": int(limit),
        }
        if cursor is not None:
            body["cursor"] = cursor
        log.info(
            "api.sync_transactions",
            external_user_id=external_user_id,
            merchant_id=merchant_id,
            has_cursor=cursor is not None,
            limit=limit,
        )
        data = await self._request("POST", "/transactions/sync", json_body=body)
        return data if isinstance(data, dict) else {}

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        log.info("api.get_transaction", transaction_id=transaction_id)
        data = await self._request("GET", f"/transactions/{transaction_id}")
        return data if isinstance(data, dict) else {}

    async def get_accounts(self, external_user_id: str) -> dict[str, Any]:
        log.info("api.get_accounts", external_user_id=external_user_id)
        data = await self._request(
            "GET", "/accounts/get", params={"external_user_id": external_user_id}
        )
        return data if isinstance(data, dict) else {}

    async def dev_simulate_link(
        self,
        *,
        external_user_id: str,
        merchant_id: int,
        new: bool = True,
        updated: bool = False,
    ) -> dict[str, Any]:
        if self.environment != "development":
            raise KnotConfigError(
                "dev_simulate_link can only be used with KNOT_ENVIRONMENT=development"
            )
        body = {
            "external_user_id": external_user_id,
            "merchant_id": int(merchant_id),
            "transactions": {"new": bool(new), "updated": bool(updated)},
        }
        log.info("api.dev_simulate_link", **body)
        data = await self._request("POST", "/development/accounts/link", json_body=body)
        return data if isinstance(data, dict) else {}


# ── Module-level singleton (lazy) ────────────────────────────────────────

_singleton: Optional[KnotClient] = None


def get_knot_client() -> KnotClient:
    global _singleton
    if _singleton is None:
        _singleton = KnotClient()
        log.info(
            "client.initialized",
            environment=_singleton.environment,
            base_url=_singleton.base_url,
            client_id_present=bool(os.getenv("KNOT_CLIENT_ID")),
            secret_present=bool(os.getenv("KNOT_SECRET")),
        )
    return _singleton


def verify_webhook_signature(
    *,
    headers: dict[str, str],
    body_fields: dict[str, Any],
    secret: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Verify the ``Knot-Signature`` header per
    https://docs.knotapi.com/webhooks#webhook-verification.

    Knot concatenates a fixed hash map with ``|`` and HMAC-SHA256s it with the
    client secret, then base64-encodes the result. We rebuild that string and
    compare against the header.

    ``body_fields`` should include only ``event`` and optionally ``session_id``
    (not every webhook has one). Returns ``(ok, error_reason)``.
    """
    import hashlib
    import hmac

    provided = (headers.get("knot-signature") or headers.get("Knot-Signature") or "").strip()
    if not provided:
        return False, "missing_header"
    client_secret = (secret or os.getenv("KNOT_SECRET") or "").strip()
    if not client_secret:
        return False, "missing_secret"

    hashmap: dict[str, str] = {
        "Content-Length": headers.get("content-length", ""),
        "Content-Type": headers.get("content-type", "application/json"),
        "Encryption-Type": "HMAC-SHA256",
        "event": str(body_fields.get("event") or ""),
    }
    if body_fields.get("session_id"):
        hashmap["session_id"] = str(body_fields["session_id"])

    basestring = "|".join(f"{k}|{v}" for k, v in hashmap.items())
    digest = hmac.new(client_secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode("ascii")
    ok = hmac.compare_digest(computed, provided)
    return ok, None if ok else "mismatch"


def log_env_check() -> dict[str, Any]:
    """One-shot env-wiring log. Called at app startup."""
    state = {
        "KNOT_ENVIRONMENT": os.getenv("KNOT_ENVIRONMENT") or "development",
        "KNOT_CLIENT_ID_present": bool(os.getenv("KNOT_CLIENT_ID")),
        "KNOT_SECRET_present": bool(os.getenv("KNOT_SECRET")),
        "KNOT_BASE_URL_override": bool(os.getenv("KNOT_BASE_URL")),
        "KNOT_WEBHOOK_PATH": os.getenv("KNOT_WEBHOOK_PATH") or "/webhooks/knot",
        "KNOT_PUBLIC_WEBHOOK_URL": os.getenv("KNOT_PUBLIC_WEBHOOK_URL") or None,
        "KNOT_VERIFY_WEBHOOKS": (os.getenv("KNOT_VERIFY_WEBHOOKS") or "0").lower() in ("1", "true", "yes"),
        "FLUX_COMPANY_ID": os.getenv("FLUX_COMPANY_ID") or None,
        "SUPABASE_URL_present": bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_SERVICE_KEY_present": bool(os.getenv("SUPABASE_SERVICE_KEY")),
    }
    log.info("env.check", **state)
    return state
