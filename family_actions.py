"""Deterministic family actions. Python owns Tesla side effects.

The LLM may phrase a result. It must not invent flash/lock/honk/climate.
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, Optional

import intents
from tesla_client import TeslaAPIError, TeslaClient

WAKE_LINES_ES = (
    "Tesla despierto.",
    "Tesla listo.",
    "Model Y despierto.",
    "Tesla Model Y listo.",
    "Despierto y en línea.",
)
WAKE_LINES_EN = (
    "Tesla is awake.",
    "Tesla Model Y ready.",
    "Tesla has been woken.",
    "Model Y online.",
    "Tesla ready.",
)


def classify(text: str) -> Optional[str]:
    """Return a direct action name or None (leave to LLM / other handlers)."""
    t = intents.fold(text)
    if not t:
        return None
    if intents.climate_temp(text) is not None:
        return "set_temp"
    if intents.is_climate_off(text):
        return "climate_off"
    if intents.is_climate_on(text):
        return "climate_on"
    if intents.is_flash(text):
        return "flash"
    if intents.is_honk(text):
        return "honk"
    if intents.is_unlock(text):
        return "unlock"
    if intents.is_lock(text):
        return "lock"
    if intents.is_wake(text):
        return "wake"
    if intents.is_day_digest(text):
        return "day_digest"
    return None


def wake_line(text: str, state: str) -> str:
    folded = intents.fold(text)
    english = bool(re.search(r"\b(wake|awake|ready)\b", folded)) and "despert" not in folded
    if state != "online":
        if english:
            return f"Wake sent. Tesla reports *{state}*, not online yet."
        return f"Mandé el wake. Tesla reporta *{state}*, todavía no online."
    pool = WAKE_LINES_EN if english else WAKE_LINES_ES
    return random.choice(pool)


def _cmd_ok(payload: Any) -> bool:
    if payload is None or isinstance(payload, str) or not isinstance(payload, dict):
        return True
    response = payload.get("response") if "response" in payload else payload
    if isinstance(response, dict) and "result" in response:
        return bool(response.get("result"))
    return True


def _cmd_reason(payload: Any) -> str:
    if isinstance(payload, dict):
        response = payload.get("response") if "response" in payload else payload
        if isinstance(response, dict):
            return str(response.get("reason") or "")
    return ""


async def execute(tesla: TeslaClient, action: str, text: str = "") -> Dict[str, Any]:
    """Run one Tesla-facing action. Never claim success if the command failed."""
    try:
        if action == "wake":
            woke = await tesla.wake_up()
            state = str((woke or {}).get("state") or "unknown")
            return {
                "ok": state == "online",
                "action": action,
                "state": state,
                "message": wake_line(text, state),
            }

        if action == "flash":
            raw = await tesla.flash_lights()
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": (
                        f"Tesla rechazó el destello ({reason}). "
                        "flash_lights solo funciona en Park."
                    ),
                }
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "message": (
                    "Destellé los faros (comando flash_lights). "
                    "Es un parpadeo corto; Tesla exige Park."
                ),
            }

        if action == "honk":
            raw = await tesla.honk_horn()
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": (
                        f"Tesla rechazó el claxon ({reason}). "
                        "honk_horn solo funciona en Park."
                    ),
                }
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "message": "Toqué el claxon (comando honk_horn). Tesla exige Park.",
            }

        if action == "lock":
            raw = await tesla.lock_doors(True)
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": f"Tesla rechazó el cierre de puertas ({reason}).",
                }
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "message": "Mandé *door_lock*. Si seguían abiertas, revisa el pin o una puerta mal cerrada.",
            }

        if action == "unlock":
            raw = await tesla.lock_doors(False)
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": f"Tesla rechazó el desbloqueo ({reason}).",
                }
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "message": "Mandé *door_unlock*.",
            }

        if action == "climate_on":
            raw = await tesla.precondition()
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": f"Tesla rechazó encender el clima ({reason}).",
                }
            verified = await _climate_flag(tesla)
            if verified is False:
                return {
                    "ok": False,
                    "action": action,
                    "message": (
                        "Tesla aceptó auto_conditioning_start, pero la telemetría "
                        "sigue en clima OFF. No invento que ya sopla aire."
                    ),
                }
            extra = "" if verified is True else " No pude releer el clima para confirmarlo."
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "message": "Encendí el clima (auto_conditioning_start)." + extra,
            }

        if action == "climate_off":
            raw = await tesla.stop_precondition()
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": f"Tesla rechazó apagar el clima ({reason}).",
                }
            verified = await _climate_flag(tesla)
            if verified is True:
                return {
                    "ok": False,
                    "action": action,
                    "message": (
                        "Tesla aceptó auto_conditioning_stop, pero la telemetría "
                        "sigue en clima ON. No digo que ya se apagó."
                    ),
                }
            extra = "" if verified is False else " No pude releer el clima para confirmarlo."
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "message": "Apagué el clima (auto_conditioning_stop)." + extra,
            }

        if action == "set_temp":
            temp = intents.climate_temp(text)
            if temp is None:
                return {
                    "ok": False,
                    "action": action,
                    "message": "No vi una temperatura. Ejemplo: *clima 18*.",
                }
            raw = await tesla.set_temps(temp, temp)
            if not _cmd_ok(raw):
                reason = _cmd_reason(raw) or "result=false"
                return {
                    "ok": False,
                    "action": action,
                    "error": reason,
                    "message": f"Tesla rechazó set_temps a {temp:.0f}°C ({reason}).",
                }
            started = await tesla.precondition()
            return {
                "ok": True,
                "action": action,
                "result": raw,
                "started": started,
                "message": (
                    f"Pedí *{temp:.0f}°C* (set_temps) y encendí el clima. "
                    "El carro aplica el setpoint; no invento la temperatura de cabina."
                ),
            }

        return {"ok": False, "action": action, "message": f"Acción desconocida: {action}"}
    except TeslaAPIError as exc:
        return {
            "ok": False,
            "action": action,
            "error": str(exc),
            "message": f"No pude hablar con el carro: {exc}",
        }
    except AttributeError as exc:
        return {
            "ok": False,
            "action": action,
            "error": str(exc),
            "message": (
                f"Este tesla_client no expone la función de {action} ({exc}). "
                "No invento que el carro ya lo hizo."
            ),
        }


async def _climate_flag(tesla: TeslaClient) -> Optional[bool]:
    try:
        snap = await tesla.get_vehicle_data(wake=False)
    except TeslaAPIError:
        return None
    flag = snap.get("is_climate_on")
    if flag is None:
        return None
    return bool(flag)


async def handle_direct(
    tesla: TeslaClient,
    text: str,
    *,
    logger: Any = None,
) -> Optional[str]:
    """If the bubble is a known car action, run it and return family copy."""
    action = classify(text)
    if action is None:
        return None
    print(f"[direct] {action} ← {text!r}")
    if action == "day_digest":
        if logger is None:
            return "No tengo el logger de viajes en este proceso."
        return format_day_digest(logger)
    result = await execute(tesla, action, text)
    return result.get("message") or "Listo."


def format_day_digest(logger: Any) -> str:
    digest = logger.get_day_digest() if hasattr(logger, "get_day_digest") else logger.get_summary("today")
    count = digest.get("trip_count") or 0
    km = digest.get("total_distance_km") or 0
    used = digest.get("battery_used_pct")
    left = digest.get("last_battery_end")
    energy = digest.get("total_energy_kwh") or 0
    cost = digest.get("total_cost_cop") or 0
    used_s = f"{used:.1f}%" if used is not None else "—"
    left_s = f"{left:.0f}%" if left is not None else "—"
    return (
        f"📊 *Hoy*\n"
        f"• Viajes: *{count}*\n"
        f"• Distancia: *{km}* km\n"
        f"• Batería usada: *{used_s}*\n"
        f"• Batería al último viaje: *{left_s}*\n"
        f"• Energía est.: *{energy}* kWh · COP {cost}"
    )
