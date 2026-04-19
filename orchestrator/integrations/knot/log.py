"""
Structured stdout logger for the Knot integration.

All Knot-related side effects (env wiring, webhook receipt, SDK session
creation, account link, login, logout, sync pages, errors) flow through
this logger so the operator can watch the backend terminal in real time.

Frontend code never imports this and never sees these logs.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

_LOGGER_NAME = "flux.knot"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [knot] [%(levelname)s] %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(os.getenv("KNOT_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


_log = _build_logger()


def _kv(extra: dict[str, Any] | None) -> str:
    if not extra:
        return ""
    safe: dict[str, Any] = {}
    for k, v in extra.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
        else:
            try:
                safe[k] = json.loads(json.dumps(v, default=str))
            except Exception:
                safe[k] = str(v)
    return " " + " ".join(f"{k}={json.dumps(v)}" for k, v in safe.items())


def info(msg: str, **extra: Any) -> None:
    _log.info(msg + _kv(extra))


def warn(msg: str, **extra: Any) -> None:
    _log.warning(msg + _kv(extra))


def error(msg: str, **extra: Any) -> None:
    _log.error(msg + _kv(extra))


def debug(msg: str, **extra: Any) -> None:
    _log.debug(msg + _kv(extra))
