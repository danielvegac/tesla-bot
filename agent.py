"""Family agent: natural language in, live Tesla tools, ES or EN out.

Source and comments are English. The model mirrors the user's language.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from llm import LLMClient, LLMError
from tesla_client import TeslaAPIError, TeslaClient
import places

SYSTEM = """You are the AI of this Tesla Model Y in Colombia. The family is talking TO THE CAR, not to a generic chatbot.
Speak as the car's assistant: "estoy al 66%", "puedo llegar", "te mando Unicentro al mapa". Warm, first-person about the vehicle.

Language: answer in the SAME language as the user (Spanish or English). Do not mix.
Tone: ChatGPT-style helper, 4–8 short sentences. Not a one-liner. Not an essay. Not a command list unless asked.

Facts: NEVER invent battery %, range, lock, location, or arrival %. Only tool results.
If a tool fails, say you do not have live data right now.

When they ask if you can reach a place:
1. get_vehicle
2. estimate_trip
3. Tell current %, rated range, driving km, estimated arrival %.
4. Label arrival % as our estimate (not Tesla's in-car planner).
5. If it looks comfortable, ask if they want you to put it on the car map.
6. send_navigation only after they confirm (sí, si, yes, mándalo, envialo, send it).

Exact commands still work outside this agent: luces, clima, carga 80, estado.
Never reveal tokens or keys."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_vehicle",
            "description": "Live Model Y snapshot: battery, range, park/drive, charge, climate, lock, lat/lon if present.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_trip",
            "description": "Geocode a destination, driving distance from the car, estimated arrival battery %. Not Tesla official planner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "Place name, e.g. Unicentro, El Rancho, address in Bogotá",
                    }
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_navigation",
            "description": "Send a destination to the Model Y map. Only after the user confirms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "True only if the user just confirmed this send.",
                    },
                },
                "required": ["destination", "confirmed"],
            },
        },
    },
]

MAX_HISTORY = 12


def _public_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "vin",
        "display_name",
        "state",
        "drive_state_label",
        "shift_state",
        "battery_level",
        "battery_range_km",
        "charge_limit_soc",
        "charging_state",
        "odometer_km",
        "latitude",
        "longitude",
        "inside_temp",
        "outside_temp",
        "is_climate_on",
        "locked",
        "demo",
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

    @property
    def enabled(self) -> bool:
        return self.llm.configured

    async def reply(self, user_text: str, chat_id: str = "family") -> str:
        if not self.enabled:
            return (
                "AI agent is not configured. Set OPENROUTER_API_KEY and LLM_MODEL, "
                "or use commands: estado, luces, ayuda."
            )
        history = list(self._history[chat_id])
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        try:
            final = ""
            for _ in range(4):
                msg = await self.llm.chat(messages, TOOLS, max_tokens=900)
                tool_calls = msg.get("tool_calls") or []
                content = (msg.get("content") or "").strip()
                if not tool_calls:
                    final = content or "No pude armar una respuesta. Prueba: estado"
                    break
                messages.append(msg)
                for call in tool_calls:
                    name = (call.get("function") or {}).get("name") or ""
                    call_id = call.get("id") or "tool"
                    result = await self._run_tool(name, _args(call))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            else:
                final = "Tardé demasiado pidiendo datos. Prueba otra vez o escribe estado."
            self._history[chat_id].append({"role": "user", "content": user_text})
            self._history[chat_id].append({"role": "assistant", "content": final})
            return final
        except LLMError as exc:
            return f"No pude hablar con el modelo ({exc}). Usa `estado` mientras tanto."
        except TeslaAPIError as exc:
            return f"Tesla no respondió: {exc}"

    async def _run_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[Agent tool] {name} {args}")
        if name == "get_vehicle":
            data = await self.tesla.get_vehicle_data()
            snap = _public_snapshot(data)
            self._last_vehicle = snap
            return {"ok": True, "vehicle": snap}
        if name == "estimate_trip":
            return await self._estimate_trip(str(args.get("destination") or ""))
        if name == "send_navigation":
            dest = str(args.get("destination") or "").strip()
            confirmed = bool(args.get("confirmed"))
            if not dest:
                return {"ok": False, "error": "empty destination"}
            if not confirmed:
                return {
                    "ok": False,
                    "needs_confirm": True,
                    "destination": dest,
                    "message": "Ask the user to confirm before sending to the car map.",
                }
            try:
                result = await self.tesla.send_navigation(dest)
                return {"ok": True, "sent": dest, "result": result}
            except TeslaAPIError as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": f"unknown tool {name}"}

    async def _estimate_trip(self, destination: str) -> Dict[str, Any]:
        dest = places.resolve_place(destination)
        if not dest:
            return {"ok": False, "error": f"could not geocode {destination}"}
        vehicle = self._last_vehicle
        if vehicle is None:
            data = await self.tesla.get_vehicle_data()
            vehicle = _public_snapshot(data)
            self._last_vehicle = vehicle
        lat, lon = vehicle.get("latitude"), vehicle.get("longitude")
        route_km = None
        if lat is not None and lon is not None:
            route_km = places.driving_km((float(lat), float(lon)), (dest["lat"], dest["lon"]))
        estimate = places.estimate_arrival_soc(
            vehicle.get("battery_level"),
            vehicle.get("battery_range_km"),
            route_km,
        )
        return {
            "ok": True,
            "destination": dest,
            "vehicle_battery_pct": vehicle.get("battery_level"),
            "vehicle_range_km": vehicle.get("battery_range_km"),
            "has_gps": lat is not None,
            "estimate": estimate,
        }
