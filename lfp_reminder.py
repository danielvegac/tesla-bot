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


def _path(path: Optional[Path] = None) -> Path:
    return path or STATE_PATH


def _load(path: Optional[Path] = None) -> Dict[str, Any]:
    target = _path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text())
    except Exception:
        return {}


def _save(data: Dict[str, Any], path: Optional[Path] = None) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data))


def on_snapshot(
    snap: Dict[str, Any],
    *,
    now: Optional[float] = None,
    path: Optional[Path] = None,
) -> Optional[str]:
    """Update weekly-full state from a live online snapshot.

    First successful SOC writes logs/lfp_full.json (seed). A nudge is
    returned only after DAYS below FULL_SOC and outside COOLDOWN_SEC.
    """
    soc = snap.get("battery_level")
    if soc is None:
        return None
    clock = time.time() if now is None else float(now)
    state = _load(path)
    if float(soc) >= FULL_SOC:
        state["last_full_at"] = clock
        state["last_full_soc"] = float(soc)
        state["seeded"] = False
        _save(state, path)
        print(f"[lfp] recorded full charge soc={float(soc):.0f}")
        return None
    last = float(state.get("last_full_at") or 0)
    if last <= 0:
        state["last_full_at"] = clock
        state["last_full_soc"] = float(soc)
        state["seeded"] = True
        _save(state, path)
        print(f"[lfp] seeded last_full_at soc={float(soc):.0f} path={_path(path)}")
        return None
    days = (clock - last) / 86400.0
    if days < DAYS:
        return None
    notified = float(state.get("last_nudge_at") or 0)
    if clock - notified < COOLDOWN_SEC:
        return None
    state["last_nudge_at"] = clock
    _save(state, path)
    print(f"[lfp] weekly nudge after {int(days)} days")
    return (
        f"Llevo {int(days)} días sin una carga llena. "
        "En LFP un 100% de vez en cuando ayuda a que el porcentaje sea honesto."
    )
