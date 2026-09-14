"""Offline evals: intents + direct-path honesty. No live Tesla, no OpenRouter.

  python3 -m evals.run
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import family_actions
import intents
from agent import FamiliaAgent
from tesla_client import TeslaAPIError

ROOT = Path(__file__).resolve().parent


class BoomLLM:
    """If a direct action reaches the model, the suite must fail."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("LLM called on a direct family action")


class FakeTesla:
    def __init__(
        self,
        state: str = "asleep",
        *,
        climate_on: bool = False,
        locked: bool = True,
        apply_climate: bool = True,
    ) -> None:
        self.vin = "LRWYGCFJ0TC568877"
        self.state = state
        self.climate_on = climate_on
        self.locked = locked
        self.apply_climate = apply_climate
        self.writes = []

    def _require_online(self, command: str):
        if self.state != "online":
            raise TeslaAPIError(
                f"Tesla API error 500 on POST command/{command}: "
                'vehicle unavailable: vehicle is offline or asleep',
                status_code=500,
            )

    async def list_vehicles(self):
        return [{"vin": self.vin, "state": self.state, "id": 1}]

    async def get_vehicle_data(self, wake: bool = True):
        if self.state != "online":
            raise TeslaAPIError("asleep", status_code=408)
        return {
            "vin": self.vin,
            "state": "online",
            "battery_level": 58,
            "battery_range_km": 150,
            "locked": self.locked,
            "is_climate_on": self.climate_on,
            "drive_state_label": "parked",
            "shift_state": "P",
        }

    async def wake_up(self):
        self.writes.append(("wake", True))
        self.state = "online"
        return {"state": "online"}

    async def lock_doors(self, lock: bool = True):
        self._require_online("door_lock" if lock else "door_unlock")
        self.writes.append(("lock", lock))
        self.locked = lock
        return {"response": {"result": True, "reason": ""}}

    async def precondition(self, minutes: int = 20):
        self._require_online("auto_conditioning_start")
        self.writes.append(("climate_on", minutes))
        if self.apply_climate:
            self.climate_on = True
        return {"response": {"result": True, "reason": ""}}

    async def stop_precondition(self):
        self._require_online("auto_conditioning_stop")
        self.writes.append(("climate_off", True))
        if self.apply_climate:
            self.climate_on = False
        return {"response": {"result": True, "reason": ""}}

    async def send_navigation(self, destination: str):
        self.writes.append(("nav", destination))
        return f"navigate:{destination}"

    async def flash_lights(self):
        self._require_online("flash_lights")
        self.writes.append(("flash", True))
        return {"response": {"result": True, "reason": ""}}

    async def honk_horn(self):
        self._require_online("honk_horn")
        self.writes.append(("honk", True))
        return {"response": {"result": True, "reason": ""}}

    async def set_temps(self, driver_c, passenger_c=None):
        self._require_online("set_temps")
        self.writes.append(("set_temps", float(driver_c)))
        return {"response": {"result": True, "reason": ""}}


class FakeLogger:
    def get_day_digest(self):
        return {
            "trip_count": 4,
            "total_distance_km": 12.3,
            "battery_used_pct": 3.0,
            "last_battery_end": 58,
            "total_energy_kwh": 1.8,
            "total_cost_cop": 1170,
        }


def _intent_kind(text: str) -> str:
    if intents.is_confirm(text) and family_actions.classify(text) is None:
        return "confirm"
    if intents.is_deny(text) and family_actions.classify(text) is None:
        return "deny"
    action = family_actions.classify(text)
    if action:
        return action
    if intents.is_wake(text):
        return "wake"
    return "other"


def eval_intents() -> list:
    cases = json.loads((ROOT / "cases.json").read_text())["intents"]
    rows = []
    for case in cases:
        got = _intent_kind(case["text"])
        rows.append(
            {
                "id": case["id"],
                "ok": got == case["expect"],
                "got": got,
                "expect": case["expect"],
                "text": case["text"],
            }
        )
    return rows


async def _route(tesla, text, llm: BoomLLM, logger=None):
    """Same split as main.on_text: direct first. LLM is a tripwire."""
    direct = await family_actions.handle_direct(tesla, text, logger=logger)
    if direct is not None:
        return {"path": "direct", "message": direct, "llm_calls": llm.calls}
    await llm.complete(text)
    return {"path": "llm", "message": None, "llm_calls": llm.calls}


async def eval_direct() -> list:
    payload = json.loads((ROOT / "cases.json").read_text())
    rows = []
    for case in payload.get("direct", []):
        tesla = FakeTesla("online")
        llm = BoomLLM()
        logger = FakeLogger() if case["action"] == "day_digest" else None
        routed = await _route(tesla, case["text"], llm, logger=logger)
        write = tuple(case["write"])
        rows.append(
            {
                "id": case["id"],
                "ok": (
                    routed["path"] == "direct"
                    and routed["llm_calls"] == 0
                    and family_actions.classify(case["text"]) == case["action"]
                    and write in tesla.writes
                    and routed["message"]
                ),
                "got": {
                    "path": routed["path"],
                    "llm_calls": routed["llm_calls"],
                    "writes": tesla.writes,
                    "preview": (routed["message"] or "")[:80],
                },
            }
        )
    return rows


async def eval_honesty() -> list:
    rows = []

    asleep = FakeTesla("asleep")
    flash = await family_actions.execute(asleep, "flash", "flash")
    rows.append(
        {
            "id": "asleep-flash-honest",
            "ok": flash.get("ok") is False and "unavailable" in (flash.get("error") or flash.get("message") or "").lower(),
            "got": flash,
        }
    )

    stale = FakeTesla("online", locked=True)
    lock = await family_actions.execute(stale, "lock", "Block doors")
    rows.append(
        {
            "id": "stale-lock-still-posts",
            "ok": lock.get("ok") is True and ("lock", True) in stale.writes,
            "got": {"ok": lock.get("ok"), "writes": stale.writes},
        }
    )

    liar = FakeTesla("online", climate_on=True, apply_climate=False)
    off = await family_actions.execute(liar, "climate_off", "Apaga el aire")
    text = (off.get("message") or "").lower()
    rows.append(
        {
            "id": "climate-off-no-lie",
            "ok": (
                ("climate_off", True) in liar.writes
                and off.get("ok") is False
                and "on" in text
                and "apag" in text
            ),
            "got": off,
        }
    )

    ok_climate = FakeTesla("online", climate_on=True, apply_climate=True)
    stopped = await family_actions.execute(ok_climate, "climate_off", "Apaga el clima")
    rows.append(
        {
            "id": "climate-off-reread-off",
            "ok": stopped.get("ok") is True and ok_climate.climate_on is False,
            "got": {"ok": stopped.get("ok"), "climate_on": ok_climate.climate_on},
        }
    )

    status = FakeTesla("online")
    llm = BoomLLM()
    leftover = await _route(status, "hay pila?", llm)
    rows.append(
        {
            "id": "status-not-direct",
            "ok": leftover["path"] == "llm" and leftover["llm_calls"] == 1 and not status.writes,
            "got": leftover,
        }
    )

    return rows


async def eval_tools() -> list:
    rows = []
    asleep = FamiliaAgent(tesla=FakeTesla("asleep"))
    asleep.llm.api_key = ""
    read = await asleep._run_tool("family", "get_vehicle", {})
    rows.append(
        {
            "id": "asleep-no-battery",
            "ok": bool(read.get("asleep")) and "battery_level" not in (read.get("vehicle") or {}),
            "got": read,
        }
    )
    woke = await asleep._run_tool("family", "wake_vehicle", {})
    rows.append(
        {
            "id": "wake-sets-online",
            "ok": woke.get("state") == "online" and woke.get("vehicle", {}).get("battery_level") == 58,
            "got": {"state": woke.get("state"), "battery": woke.get("vehicle", {}).get("battery_level")},
        }
    )
    pending = await asleep._run_tool("family", "unlock_doors", {"confirmed": False})
    rows.append(
        {
            "id": "unlock-needs-confirm",
            "ok": pending.get("needs_confirm") is True and not any(w[0] == "lock" and w[1] is False for w in asleep.tesla.writes),
            "got": pending,
        }
    )
    done = await asleep._run_tool("family", "unlock_doors", {"confirmed": True})
    rows.append(
        {
            "id": "unlock-after-confirm",
            "ok": done.get("ok") is True and ("lock", False) in asleep.tesla.writes,
            "got": {"ok": done.get("ok"), "writes": asleep.tesla.writes},
        }
    )
    return rows


def _print(title: str, rows: list) -> int:
    print(f"\n== {title} ==")
    failed = 0
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        if not row["ok"]:
            failed += 1
        print(f"  {mark}  {row['id']}")
        if not row["ok"]:
            print(f"        {row}")
    return failed


async def main() -> int:
    failed = _print("intents", eval_intents())
    failed += _print("direct", await eval_direct())
    failed += _print("honesty", await eval_honesty())
    failed += _print("tools", await eval_tools())
    print(f"\n{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
