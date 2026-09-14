"""Weekly full-charge nudge for this LFP Model Y."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

STATE_PATH = Path("logs/lfp_full.json")
FULL_SOC = 99
DAYS = 7
COOLDOWN_SEC = 20 * 3600


def _load() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data))


def on_snapshot(snap: Dict[str, Any]) -> Optional[str]:
    soc = snap.get("battery_level")
    if soc is None:
        return None
    now = time.time()
    state = _load()
    if float(soc) >= FULL_SOC:
        state["last_full_at"] = now
        state["last_full_soc"] = float(soc)
        _save(state)
        return None
    last = float(state.get("last_full_at") or 0)
    if last <= 0:
        state["last_full_at"] = now
        state["seeded"] = True
        _save(state)
        return None
    days = (now - last) / 86400.0
    if days < DAYS:
        return None
    notified = float(state.get("last_nudge_at") or 0)
    if now - notified < COOLDOWN_SEC:
        return None
    state["last_nudge_at"] = now
    _save(state)
    return (
        f"Llevo {int(days)} días sin una carga llena. "
        "En LFP un 100% de vez en cuando ayuda a que el porcentaje sea honesto."
    )
