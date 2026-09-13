"""Family agent: natural language in, live Tesla tools, ES or EN out."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from llm import LLMClient, LLMError
from tesla_client import TeslaAPIError, TeslaClient
import places
import eventlog

SYSTEM = """You are this Tesla Model Y talking to the family in Colombia.
First person as the car. Same language as the user. 2 to 4 short sentences.

Honesty:
- Never invent battery, range, GPS, lock, climate, or awake/asleep.
- Use only the latest tool JSON. If ok=false, say you could not reach the car.
- If state is asleep/offline, say you are asleep. Do not reuse old battery numbers.
- get_vehicle does not wake you. To wake, call wake_vehicle.
- Unlock and navigation need confirm. Lock and climate run immediately.
- If a lock tool returns already=true, say the doors were already in that state. Do not claim you just changed them.
Never reveal tokens."""

CONFIRM_WRITES = {"unlock_doors"}
WRITE_TOOLS = {"lock_doors", "unlock_doors", "climate_on", "climate_off"}

TOOLS = [
    {"type": "function", "function": {"name": "get_vehicle", "description": "Read snapshot WITHOUT waking.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "wake_vehicle", "description": "Wake the car, then read battery.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "estimate_trip", "description": "Distance + estimated arrival %.", "parameters": {"type": "object", "properties": {"destination": {"type": "string"}}, "required": ["destination"]}}},
    {"type": "function", "function": {"name": "send_navigation", "description": "Send destination to the map after confirm.", "parameters": {"type": "object", "properties": {"destination": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["destination", "confirmed"]}}},
    {"type": "function", "function": {"name": "lock_doors", "description": "Lock doors immediately. If already locked, report already=true.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "unlock_doors", "description": "Unlock doors. Needs confirm. If already unlocked, report already=true.", "parameters": {"type": "object", "properties": {"confirmed": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "climate_on", "description": "Start climate immediately.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "climate_off", "description": "Stop climate immediately.", "parameters": {"type": "object", "properties": {}}}},
]

MAX_HISTORY = 8
CONFIRM_RE = re.compile(r"^(si|s[ií]|yes|ok|okay|dale|claro|mando|mandalo|envialo|send it|send)\b", re.I)
DENY_RE = re.compile(r"^(no|nop|cancel|cancela|cancelar|stop)\b", re.I)
LABELS = {
    "unlock_doors": {"es": "abrir las puertas", "en": "unlock the doors"},
    "send_navigation": {"es": "mandarlo al mapa", "en": "send it to the map"},
}
MESSAGES = {
    "lock_doors": "Listo. Ya cerré las puertas.",
    "unlock_doors": "Listo. Ya abrí las puertas.",
    "climate_on": "Listo. Encendí el clima.",
    "climate_off": "Listo. Apagué el clima.",
    "lock_already": "Las puertas ya estaban cerradas.",
    "unlock_already": "Las puertas ya estaban abiertas.",
}


def _fold(text: str) -> str:
    n = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in n if unicodedata.category(c) != "Mn").strip().lower()


def _is_confirm(text: str) -> bool:
    t = _fold(text).replace(",", " ")
    return bool(CONFIRM_RE.search(t)) or "mandalo" in t or "envialo" in t or "send it" in t


def _is_deny(text: str) -> bool:
    return bool(DENY_RE.search(_fold(text)))


def _english(text: str) -> bool:
    t = _fold(text)
    return bool(re.search(r"\b(lock|unlock|climate|wake|yes|please|the|doors)\b", t))


def _public_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "vin", "display_name", "state", "drive_state_label", "shift_state",
        "battery_level", "battery_range_km", "charge_limit_soc", "charging_state",
        "odometer_km", "latitude", "longitude", "inside_temp", "outside_temp",
        "is_climate_on", "locked", "demo",
    )
    return {k: data.get(k) for k in keys}


def _args(call: Dict[str, Any]) -> Dict[str, Any]:
    raw = (call.get("function") or {}).get("arguments") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


class FamiliaAgent:
    def __init__(self, tesla: Optional[TeslaClient] = None, llm: Optional[LLMClient] = None):
        self.tesla = tesla or TeslaClient()
        self.llm = llm or LLMClient()
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))
        self._last_vehicle: Optional[Dict[str, Any]] = None
        self._pending_nav: Optional[str] = None
        self._pending_write: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.llm.configured

    def _ask_confirm(self, tool: str, user_text: str) -> str:
        lang = "en" if _english(user_text) else "es"
        label = LABELS.get(tool, {}).get(lang, tool)
        if lang == "en":
            return f"I can {label}. Say *yes* to do it, or *no* to cancel."
        return f"Puedo {label}. Di *sí* para hacerlo, o *no* para cancelar."

    async def reply(self, user_text: str, chat_id: str = "family") -> str:
        if not self.enabled:
            return "AI agent is not configured. Use commands: estado, luces, ayuda."

        if self._pending_write and _is_deny(user_text):
            self._pending_write = None
            self._pending_nav = None
            final = "Ok, cancelled." if _english(user_text) else "Listo, cancelado."
            self._history[chat_id].append({"role": "user", "content": user_text})
            self._history[chat_id].append({"role": "assistant", "content": final})
            return final

        if self._pending_write and _is_confirm(user_text):
            tool = self._pending_write
            print(f"[Agent] confirm {tool}")
            eventlog.log_event("confirm", tool=tool)
            result = await self._run_tool(tool, {"confirmed": True})
            self._pending_write = None
            final = result.get("message") or (
                f"No pude completar la acción: {result.get('error') or result}"
                if not result.get("ok")
                else "Listo."
            )
            self._history[chat_id].append({"role": "user", "content": user_text})
            self._history[chat_id].append({"role": "assistant", "content": final})
            return final

        if self._pending_nav and _is_confirm(user_text):
            dest = self._pending_nav
            print(f"[Agent] confirm send_navigation {dest}")
            result = await self._run_tool("send_navigation", {"destination": dest, "confirmed": True})
            if result.get("ok"):
                self._pending_nav = None
                final = f"Listo. Ya mandé *{dest}* al mapa del Y. Revisa la pantalla del carro."
            else:
                final = f"Quise mandar *{dest}* al mapa pero Tesla dijo: {result.get('error') or result}"
            self._history[chat_id].append({"role": "user", "content": user_text})
            self._history[chat_id].append({"role": "assistant", "content": final})
            return final

        history = list(self._history[chat_id])
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        try:
            final = ""
            pending_ask = None
            immediate = None
            for _ in range(4):
                msg = await self.llm.chat(messages, TOOLS, max_tokens=1600)
                tool_calls = msg.get("tool_calls") or []
                content = (msg.get("content") or "").strip()
                if not tool_calls:
                    if not content:
                        nudge = await self.llm.chat(
                            messages + [{"role": "user", "content": "Answer in 2-4 sentences using only the latest tool JSON."}],
                            None,
                            max_tokens=400,
                        )
                        content = (nudge.get("content") or "").strip()
                    final = pending_ask or immediate or content or "No pude armar una respuesta honesta. Prueba estado."
                    break
                messages.append(msg)
                for call in tool_calls:
                    name = (call.get("function") or {}).get("name") or ""
                    result = await self._run_tool(name, _args(call))
                    if result.get("needs_confirm"):
                        pending_ask = self._ask_confirm(name, user_text)
                    elif result.get("message") and name in WRITE_TOOLS:
                        immediate = result.get("message")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or "tool",
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            else:
                final = pending_ask or immediate or "Tardé pidiendo datos. Escribe estado."
            self._history[chat_id].append({"role": "user", "content": user_text})
            self._history[chat_id].append({"role": "assistant", "content": final})
            eventlog.log_event("turn", text=user_text[:200], preview=str(final)[:200])
            return final
        except LLMError as exc:
            return f"No pude hablar con el modelo ({exc}). Usa `estado`."
        except TeslaAPIError as exc:
            return f"No pude hablar con el carro: {exc}"

    async def _fleet_state(self) -> str:
        try:
            vehicles = await self.tesla.list_vehicles()
        except TeslaAPIError:
            return "unknown"
        vin = (getattr(self.tesla, "vin", "") or "").upper()
        match = None
        for v in vehicles or []:
            if str(v.get("vin", "")).upper() == vin:
                match = v
                break
        if match is None and vehicles:
            match = vehicles[0]
        return str((match or {}).get("state") or "unknown")

    async def _current_locked(self) -> Optional[bool]:
        if self._last_vehicle and self._last_vehicle.get("locked") is not None:
            return bool(self._last_vehicle.get("locked"))
        try:
            state = await self._fleet_state()
            if state != "online":
                return None
            snap = _public_snapshot(await self.tesla.get_vehicle_data(wake=False))
            self._last_vehicle = snap
            if snap.get("locked") is None:
                return None
            return bool(snap.get("locked"))
        except TeslaAPIError:
            return None

    async def _guarded_write(self, name: str, confirmed: bool, runner) -> Dict[str, Any]:
        if name in CONFIRM_WRITES and not confirmed:
            self._pending_write = name
            return {"ok": False, "needs_confirm": True, "action": name}
        if name in {"lock_doors", "unlock_doors"}:
            locked = await self._current_locked()
            if locked is True and name == "lock_doors":
                return {"ok": True, "already": True, "locked": True, "message": MESSAGES["lock_already"]}
            if locked is False and name == "unlock_doors":
                return {"ok": True, "already": True, "locked": False, "message": MESSAGES["unlock_already"]}
        try:
            result = await runner()
            self._pending_write = None
            if name == "lock_doors":
                if self._last_vehicle is not None:
                    self._last_vehicle["locked"] = True
            if name == "unlock_doors":
                if self._last_vehicle is not None:
                    self._last_vehicle["locked"] = False
            return {"ok": True, "already": False, "result": result, "message": MESSAGES.get(name, "Listo.")}
        except TeslaAPIError as exc:
            return {"ok": False, "error": str(exc)}

    async def _run_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[Agent tool] {name} {args}")
        eventlog.log_event("tool", name=name, args=args)
        if name == "get_vehicle":
            try:
                state = await self._fleet_state()
                if state != "online":
                    snap = {"state": state}
                    self._last_vehicle = snap
                    return {"ok": True, "asleep": True, "vehicle": snap, "note": "Do not quote old battery figures."}
                data = await self.tesla.get_vehicle_data(wake=False)
                snap = _public_snapshot(data)
                self._last_vehicle = snap
                return {"ok": True, "asleep": False, "vehicle": snap}
            except TeslaAPIError as exc:
                if exc.status_code == 408:
                    return {"ok": True, "asleep": True, "vehicle": {"state": "asleep"}, "note": "Do not quote old battery figures."}
                return {"ok": False, "error": str(exc)}
        if name == "wake_vehicle":
            try:
                woke = await self.tesla.wake_up()
                state = (woke or {}).get("state") or "unknown"
                snap: Dict[str, Any] = {"state": state}
                if state == "online":
                    try:
                        snap = _public_snapshot(await self.tesla.get_vehicle_data(wake=False))
                    except TeslaAPIError as exc:
                        return {"ok": False, "state": state, "error": f"woke but could not read data: {exc}"}
                self._last_vehicle = snap
                return {"ok": state == "online", "state": snap.get("state") or state, "vehicle": snap}
            except TeslaAPIError as exc:
                return {"ok": False, "error": str(exc)}
        if name == "estimate_trip":
            result = await self._estimate_trip(str(args.get("destination") or ""))
            dest = ((result.get("destination") or {}).get("query")) or args.get("destination")
            if result.get("ok") and dest:
                self._pending_nav = str(dest)
            return result
        if name == "send_navigation":
            dest = str(args.get("destination") or "").strip()
            if not dest:
                return {"ok": False, "error": "empty destination"}
            if not args.get("confirmed"):
                self._pending_nav = dest
                return {"ok": False, "needs_confirm": True, "destination": dest}
            try:
                sent = await self.tesla.send_navigation(dest)
                self._pending_nav = None
                return {"ok": True, "sent": dest, "result": sent}
            except TeslaAPIError as exc:
                return {"ok": False, "error": str(exc)}
        if name in WRITE_TOOLS:
            runners = {
                "lock_doors": lambda: self.tesla.lock_doors(True),
                "unlock_doors": lambda: self.tesla.lock_doors(False),
                "climate_on": self.tesla.precondition,
                "climate_off": self.tesla.stop_precondition,
            }
            return await self._guarded_write(name, bool(args.get("confirmed")), runners[name])
        return {"ok": False, "error": f"unknown tool {name}"}

    async def _estimate_trip(self, destination: str) -> Dict[str, Any]:
        dest = places.resolve_place(destination)
        if not dest:
            return {"ok": False, "error": f"could not geocode {destination}"}
        vehicle = self._last_vehicle
        if vehicle is None or vehicle.get("state") != "online":
            try:
                vehicle = _public_snapshot(await self.tesla.get_vehicle_data())
                self._last_vehicle = vehicle
            except TeslaAPIError as exc:
                return {"ok": False, "error": str(exc)}
        lat, lon = vehicle.get("latitude"), vehicle.get("longitude")
        route_km = None
        if lat is not None and lon is not None:
            route_km = places.driving_km((float(lat), float(lon)), (dest["lat"], dest["lon"]))
        estimate = places.estimate_arrival_soc(
            vehicle.get("battery_level"), vehicle.get("battery_range_km"), route_km
        )
        return {
            "ok": True,
            "destination": dest,
            "vehicle_battery_pct": vehicle.get("battery_level"),
            "vehicle_range_km": vehicle.get("battery_range_km"),
            "has_gps": lat is not None,
            "estimate": estimate,
        }
