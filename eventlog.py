"""JSONL event log for agent turns. No secrets."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "agent.jsonl"
_REDACT = ("token", "authorization", "password", "secret", "api_key")


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(part in low for part in _REDACT):
                out[key] = "[redacted]"
            else:
                out[key] = _clean(item)
        return out
    if isinstance(value, list):
        return [_clean(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


def log_event(kind: str, **fields: Any) -> None:
    payload: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
    }
    payload.update(_clean(fields))
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[log] write failed: {exc}")
