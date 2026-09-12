"""Family agent: natural language in, live Tesla tools, ES/EN out.

Slice 1: get_vehicle only. Writes stay on CommandHandler.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from llm import LLMClient, LLMError
from tesla_client import TeslaAPIError, TeslaClient

SYSTEM = """Eres Tesla Familia, asistente de la familia para un Tesla Model Y en Colombia.
Responde en el mismo idioma que el usuario (español o inglés), breve y claro.
NUNCA inventes batería, rango, ubicación, puertas ni si está parked.
Si necesitas datos del carro, llama get_vehicle.
Si get_vehicle falla, di que no tienes datos live.
No ofrezcas desbloquear ni navegar en esta versión; para luces/carga/clima di que usen el comando exacto (luces, carga 80, clima).
No reveles tokens ni claves."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_vehicle",
            "description": "Live snapshot of the Model Y: battery, range, park/drive, charge, climate, lock, odometer.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }
]


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
        "inside_temp",
        "outside_temp",
        "is_climate_on",
        "locked",
        "demo",
    )
    return {k: data.get(k) for k in keys}


class FamiliaAgent:
    def __init__(self, tesla: Optional[TeslaClient] = None, llm: Optional[LLMClient] = None):
        self.tesla = tesla or TeslaClient()
        self.llm = llm or LLMClient()

    @property
    def enabled(self) -> bool:
        return self.llm.configured

    async def reply(self, user_text: str) -> str:
        if not self.enabled:
            return (
                "El agente AI no está configurado. Pon OPENROUTER_API_KEY y "
                "LLM_MODEL en .env, o usa comandos: estado, luces, ayuda."
            )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_text},
        ]
        try:
            for _ in range(3):
                msg = await self.llm.chat(messages, TOOLS, max_tokens=800)
                tool_calls = msg.get("tool_calls") or []
                content = (msg.get("content") or "").strip()
                if not tool_calls:
                    return content or "No pude armar una respuesta. Prueba: estado"
                messages.append(msg)
                for call in tool_calls:
                    name = (call.get("function") or {}).get("name") or ""
                    call_id = call.get("id") or "tool"
                    result = await self._run_tool(name)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            return "Tardé demasiado pidiendo datos. Prueba otra vez o escribe estado."
        except LLMError as exc:
            return f"No pude hablar con el modelo ({exc}). Usa `estado` mientras tanto."
        except TeslaAPIError as exc:
            return f"Tesla no respondió: {exc}"

    async def _run_tool(self, name: str) -> Dict[str, Any]:
        print(f"[Agent tool] {name}")
        if name == "get_vehicle":
            data = await self.tesla.get_vehicle_data()
            return {"ok": True, "vehicle": _public_snapshot(data)}
        return {"ok": False, "error": f"unknown tool {name}"}
