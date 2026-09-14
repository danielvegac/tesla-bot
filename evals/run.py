"""Offline evals: intents + tool honesty. No live Tesla, no OpenRouter.

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


class FakeTesla:
    def __init__(self, state: str = "asleep") -> None:
        self.vin = "LRWYGCFJ0TC568877"
        self.state = state
        self.writes = []

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
            "locked": True,
            "is_climate_on": False,
            "drive_state_label": "parked",
        }

    async def wake_up(self):
        self.state = "online"
        return {"state": "online"}

    async def lock_doors(self, lock: bool = True):
        self.writes.append(("lock", lock))
        return "doors:locked" if lock else "doors:unlocked"

    async def precondition(self, minutes: int = 20):
        self.writes.append(("climate_on", minutes))
        return "precondition_start"

    async def stop_precondition(self):
        self.writes.append(("climate_off", True))
        return "precondition_stop"

    async def send_navigation(self, destination: str):
        self.writes.append(("nav", destination))
        return f"navigate:{destination}"

    async def flash_lights(self):
        self.writes.append(("flash", True))
        return {"response": {"result": True, "reason": ""}}

    async def honk_horn(self):
        self.writes.append(("honk", True))
        return {"response": {"result": True, "reason": ""}}

    async def set_temps(self, driver_c, passenger_c=None):
        self.writes.append(("set_temps", driver_c))
        return {"response": {"result": True, "reason": ""}}


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
            "ok": pending.get("needs_confirm") is True and not asleep.tesla.writes,
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
    online = FamiliaAgent(tesla=FakeTesla("online"))
    flash = await family_actions.execute(online.tesla, "flash", "flash")
    rows.append(
        {
            "id": "direct-flash-posts",
            "ok": flash.get("ok") is True and ("flash", True) in online.tesla.writes,
            "got": flash,
        }
    )
    lock = await family_actions.execute(online.tesla, "lock", "Block doors")
    rows.append(
        {
            "id": "direct-lock-posts",
            "ok": lock.get("ok") is True and ("lock", True) in online.tesla.writes,
            "got": lock,
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
    failed += _print("tools", await eval_tools())
    print(f"\n{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
