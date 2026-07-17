"""Parse family chat commands (ES/EN) and dispatch Tesla actions + notifications."""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import config
from telegram_bot import TelegramBot
from tesla_client import TeslaAPIError, TeslaClient
from trip_logger import TripLogger

if TYPE_CHECKING:
    from trip_monitor import TripMonitor

HELP_TEXT = """🤖 *Tesla Familia* — comandos

*Auto*
• `estado` / `status` — batería, rango, clima, puertas
• `batería` / `battery` — solo nivel y carga
• `rango` / `range` — autonomía estimada
• `ubicación` / `location` — coordenadas
• `despertar` / `wake` — despertar el vehículo

*Carga*
• `carga 80` / `charge 80` — límite de carga (50–100%)
• `estado carga` / `charging` — estado del cargador

*Clima y seguridad*
• `clima` / `precondition` — encender clima
• `apagar clima` / `climate off` — apagar clima
• `bloquear` / `lock` — cerrar puertas
• `desbloquear` / `unlock` — abrir puertas
• `claxon` / `honk` — tocar bocina
• `luces` / `flash` — destellar luces

*Navegación*
• `ir a X` / `navegar X` / `go to X`

*Viajes*
• `viajes` / `trips` — últimos viajes
• `viaje activo` / `active trip` — viaje en curso
• `resumen` / `summary` — totales de hoy
• `semana` / `week` — totales 7 días
• `monitor` — estado del TripMonitor

*Bot*
• `hola` / `ping` — ¿estoy vivo?
• `notificar` / `notify` — reenviar último estado por Telegram
• `ayuda` / `help` — esta lista
• `salir` / `exit` — (solo CLI)"""


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    return _strip_accents((text or "").strip().lower())


class CommandHandler:
    def __init__(
        self,
        tesla: Optional[TeslaClient] = None,
        logger: Optional[TripLogger] = None,
        telegram: Optional[TelegramBot] = None,
        whatsapp: Optional[Any] = None,
        monitor: Optional["TripMonitor"] = None,
        notify: bool = True,
    ):
        self.tesla = tesla or TeslaClient()
        self.logger = logger or TripLogger()
        self.telegram = telegram or TelegramBot()
        self.whatsapp = whatsapp
        self.monitor = monitor
        self.notify = notify

        # Charge-reminder de-dupe state
        self._last_low_battery_notice: float = 0.0
        self._last_charge_complete_notice: float = 0.0
        self._was_charging: bool = False
        self._low_battery_active: bool = False

    def attach_monitor(self, monitor: "TripMonitor") -> None:
        self.monitor = monitor

    # ------------------------------------------------------------------
    # Public command entry
    # ------------------------------------------------------------------

    async def handle(self, message: str, *, reply_notify: bool = False) -> str:
        """Handle a user command. Returns response text (also printed).

        If reply_notify=True, also push the response via Telegram.
        """
        raw = (message or "").strip()
        if not raw:
            response = "👋 Escribe un comando. Prueba: *ayuda*"
            print(response)
            return response

        msg = _norm(raw)
        try:
            response = await self._dispatch(msg, raw)
        except TeslaAPIError as exc:
            response = (
                f"❌ *Error Tesla*\n{exc}\n"
                f"_Revisa token, VIN, región o prueba `despertar`._"
            )
        except Exception as exc:
            response = f"❌ *Error:* {exc}"

        print(response)
        if reply_notify:
            await self.notify_family(response)
        return response

    async def _dispatch(self, msg: str, raw: str) -> str:
        if self._is_help(msg):
            return HELP_TEXT

        if self._is_hello(msg):
            mode = "demo" if self.tesla.demo else "live"
            tg = "Telegram demo" if self.telegram.demo else "Telegram"
            mon = "ON" if self.monitor and self.monitor.running else "off"
            return (
                f"👋 *Hola familia!* Bot activo.\n"
                f"• Tesla: `{mode}`\n"
                f"• Avisos: `{tg}`\n"
                f"• Monitor: `{mon}`\n"
                f"Escribe `ayuda` para ver comandos."
            )

        if self._is_status(msg):
            return await self._cmd_status()

        if self._is_battery_only(msg):
            return await self._cmd_battery()

        if self._is_range(msg):
            return await self._cmd_range()

        if self._is_location(msg):
            return await self._cmd_location()

        if self._is_charging_status(msg):
            return await self._cmd_charging_status()

        if self._is_wake(msg):
            return await self._cmd_wake()

        if self._is_stop_climate(msg):
            await self.tesla.stop_precondition()
            return "🌡️ Clima *apagado*."

        if self._is_precondition(msg):
            await self.tesla.precondition()
            return "❄️ *Preacondicionando* la cabina (~20 min)."

        charge = self._parse_charge_limit(msg)
        if charge is not None:
            await self.tesla.set_charge_limit(charge)
            return (
                f"🔋 Límite de carga fijado en *{charge}%*.\n"
                f"_Tip: en casa suele bastar 70–80% día a día._"
            )

        dest = self._parse_navigation(msg, raw)
        if dest is not None:
            await self.tesla.send_navigation(dest)
            return f"🗺️ Navegación enviada a: *{dest}*"

        if self._is_unlock(msg):
            await self.tesla.lock_doors(False)
            return "🔓 Puertas *desbloqueadas*."

        if self._is_lock(msg):
            await self.tesla.lock_doors(True)
            return "🔒 Puertas *bloqueadas*."

        if self._is_honk(msg):
            await self.tesla.honk_horn()
            return "📢 *Claxon* activado."

        if self._is_flash(msg):
            await self.tesla.flash_lights()
            return "💡 *Luces* destellando."

        if self._is_active_trip(msg):
            return self._cmd_active_trip()

        if self._is_trips(msg):
            return self._cmd_trips()

        if self._is_week(msg):
            return self._format_summary(self.logger.get_summary("week"), "semana")

        if self._is_summary(msg):
            return self._format_summary(self.logger.get_summary("today"), "hoy")

        if self._is_monitor(msg):
            return self._cmd_monitor()

        if self._is_notify_push(msg):
            status = await self._cmd_status()
            await self.notify_family(status)
            return "📤 Estado enviado a la familia por Telegram.\n\n" + status

        return (
            "🤔 No entendí ese comando.\n"
            "Prueba: `estado`, `carga 80`, `clima`, `ir a Unicentro`, "
            "`viajes` o `ayuda`."
        )

    # ------------------------------------------------------------------
    # Intent matchers (ES + EN, accent-insensitive)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_help(msg: str) -> bool:
        return msg in {"help", "ayuda", "?", "comandos", "commands", "menu"}

    @staticmethod
    def _is_hello(msg: str) -> bool:
        return msg in {
            "hola",
            "hello",
            "hi",
            "ping",
            "hey",
            "buenas",
            "buenos dias",
            "buenas tardes",
            "buenas noches",
        }

    @staticmethod
    def _is_status(msg: str) -> bool:
        return msg in {
            "status",
            "estado",
            "stat",
            "info",
            "como esta",
            "como esta el carro",
            "como esta el auto",
            "vehicle",
            "carro",
            "auto",
        }

    @staticmethod
    def _is_battery_only(msg: str) -> bool:
        return msg in {"bateria", "battery", "soc", "nivel", "porcentaje"}

    @staticmethod
    def _is_range(msg: str) -> bool:
        return msg in {"rango", "range", "autonomia", "km restantes", "alcance"}

    @staticmethod
    def _is_location(msg: str) -> bool:
        return msg in {
            "ubicacion",
            "location",
            "donde esta",
            "donde esta el carro",
            "donde esta el auto",
            "gps",
            "mapa",
        }

    @staticmethod
    def _is_charging_status(msg: str) -> bool:
        return msg in {
            "estado carga",
            "charging",
            "cargando",
            "carga estado",
            "charge status",
            "charger",
            "cargador",
        }

    @staticmethod
    def _is_wake(msg: str) -> bool:
        return msg in {"wake", "despertar", "despierta", "wake up", "online"}

    @staticmethod
    def _is_precondition(msg: str) -> bool:
        if CommandHandler._is_stop_climate(msg):
            return False
        keys = (
            "precondition",
            "precondicion",
            "precondicionar",
            "clima",
            "aire",
            "cabin",
            "climatizar",
            "calentar",
            "enfriar",
        )
        if msg in {"ac", "a/c"}:
            return True
        return any(k in msg for k in keys) and "apagar" not in msg and "off" not in msg

    @staticmethod
    def _is_stop_climate(msg: str) -> bool:
        return msg in {
            "apagar clima",
            "clima off",
            "climate off",
            "stop climate",
            "stop precondition",
            "apagar aire",
            "apagar ac",
        } or (msg.startswith("apagar") and "clima" in msg)

    @staticmethod
    def _is_lock(msg: str) -> bool:
        if CommandHandler._is_unlock(msg):
            return False
        return msg in {
            "lock",
            "bloquear",
            "cerrar",
            "cerrado",
            "cierra",
            "lock doors",
            "cerrar puertas",
        } or msg.startswith("lock")

    @staticmethod
    def _is_unlock(msg: str) -> bool:
        return msg in {
            "unlock",
            "desbloquear",
            "abrir",
            "abierto",
            "abre",
            "unlock doors",
            "abrir puertas",
        } or "unlock" in msg or "desbloquear" in msg

    @staticmethod
    def _is_honk(msg: str) -> bool:
        return msg in {"honk", "claxon", "bocina", "pito", "horn", "beep"}

    @staticmethod
    def _is_flash(msg: str) -> bool:
        return msg in {
            "flash",
            "luces",
            "lights",
            "flash lights",
            "destellar",
            "parpadear",
        }

    @staticmethod
    def _is_trips(msg: str) -> bool:
        return msg in {
            "trips",
            "viajes",
            "trip",
            "viaje",
            "historial",
            "history",
            "ultimos viajes",
        }

    @staticmethod
    def _is_active_trip(msg: str) -> bool:
        return msg in {
            "viaje activo",
            "active trip",
            "trip active",
            "en viaje",
            "current trip",
        }

    @staticmethod
    def _is_summary(msg: str) -> bool:
        return msg in {
            "summary",
            "resumen",
            "totales",
            "stats",
            "estadisticas",
            "hoy",
            "today",
        }

    @staticmethod
    def _is_week(msg: str) -> bool:
        return msg in {"week", "semana", "resumen semana", "week summary", "7 dias"}

    @staticmethod
    def _is_monitor(msg: str) -> bool:
        return msg in {"monitor", "trip monitor", "monitoreo", "polling"}

    @staticmethod
    def _is_notify_push(msg: str) -> bool:
        return msg in {
            "notificar",
            "notify",
            "avisar",
            "enviar estado",
            "push",
            "telegram",
        }

    @staticmethod
    def _parse_charge_limit(msg: str) -> Optional[int]:
        patterns = [
            r"(?:carga|charge|limite)\s*(?:a\s*)?(\d{2,3})",
            r"(?:set\s+)?charge\s*(?:limit\s*)?(\d{2,3})",
            r"(\d{2,3})\s*%?\s*(?:carga|charge)",
            r"cargar\s*(?:a\s*)?(\d{2,3})",
        ]
        for pat in patterns:
            m = re.search(pat, msg)
            if m:
                pct = int(m.group(1))
                if 50 <= pct <= 100:
                    return pct
                return None  # invalid range — fall through as unknown
        return None

    @staticmethod
    def _parse_navigation(msg: str, raw: str) -> Optional[str]:
        lower = msg
        for prefix in (
            "go to ",
            "navegar a ",
            "navegar ",
            "ir a ",
            "navigate to ",
            "nav to ",
            "nav ",
            "destino ",
            "llevame a ",
            "llevar a ",
            "direccion ",
        ):
            if lower.startswith(prefix):
                idx = lower.find(prefix)
                dest = raw[idx + len(prefix) :].strip()
                return dest or "Unicentro"
        for pattern, flags in (
            (r"go to", re.I),
            (r"ir a", re.I),
            (r"navegar(?:\s+a)?", re.I),
            (r"llevame a", re.I),
        ):
            parts = re.split(pattern, raw, maxsplit=1, flags=flags)
            if len(parts) > 1 and parts[-1].strip():
                return parts[-1].strip()
        return None

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    async def _cmd_status(self) -> str:
        data = await self.tesla.get_vehicle_data()
        mode = "demo" if data.get("demo") else "live"
        drive = data.get("drive_state_label") or "—"
        shift = data.get("shift_state") or "P"
        name = data.get("display_name") or "Tesla"
        batt = data.get("battery_level")
        rng = data.get("battery_range_km")
        lines = [
            f"🚘 *{name}* `({mode})`",
            f"• Estado: *{data.get('state')}* / {drive} (marcha {shift})",
            f"• Batería: *{batt}%* · rango ~*{rng}* km",
            f"• Límite carga: {data.get('charge_limit_soc')}%",
            f"• Cargador: {data.get('charging_state') or '—'}",
            f"• Odómetro: {data.get('odometer_km')} km",
            f"• Clima: {'ON ❄️' if data.get('is_climate_on') else 'OFF'} "
            f"· cabina {data.get('inside_temp')}°C / ext {data.get('outside_temp')}°C",
            f"• Puertas: {'🔒 cerradas' if data.get('locked') else '🔓 abiertas'}",
        ]
        if data.get("latitude") is not None:
            lines.append(
                f"• Ubicación: `{data.get('latitude')}, {data.get('longitude')}`"
            )
        active = self.logger.get_active_trip()
        if active:
            lines.append(f"• Viaje activo: *#{active['id']}* desde {active.get('start_time')}")
        return "\n".join(lines)

    async def _cmd_battery(self) -> str:
        data = await self.tesla.get_vehicle_data()
        level = data.get("battery_level")
        limit = data.get("charge_limit_soc")
        state = data.get("charging_state")
        emoji = "🟢" if (level or 0) > 50 else ("🟡" if (level or 0) > 20 else "🔴")
        return (
            f"{emoji} *Batería {level}%*\n"
            f"• Límite: {limit}%\n"
            f"• Estado carga: {state}\n"
            f"• Rango: ~{data.get('battery_range_km')} km"
        )

    async def _cmd_range(self) -> str:
        data = await self.tesla.get_vehicle_data()
        return (
            f"🛣️ Autonomía estimada: *~{data.get('battery_range_km')} km*\n"
            f"(batería {data.get('battery_level')}%)"
        )

    async def _cmd_location(self) -> str:
        data = await self.tesla.get_vehicle_data()
        lat, lon = data.get("latitude"), data.get("longitude")
        if lat is None or lon is None:
            return "📍 Ubicación no disponible (vehículo dormido o sin GPS)."
        maps = f"https://maps.google.com/?q={lat},{lon}"
        return f"📍 *Ubicación*\n`{lat}, {lon}`\n{maps}"

    async def _cmd_charging_status(self) -> str:
        data = await self.tesla.get_vehicle_data()
        state = data.get("charging_state") or "—"
        power = data.get("charger_power")
        added = data.get("charge_energy_added")
        return (
            f"🔌 *Carga:* {state}\n"
            f"• Batería: {data.get('battery_level')}% / límite {data.get('charge_limit_soc')}%\n"
            f"• Potencia: {power or 0} kW\n"
            f"• Energía añadida: {added or 0} kWh"
        )

    async def _cmd_wake(self) -> str:
        result = await self.tesla.wake_up()
        state = (result or {}).get("state", "online")
        return f"☀️ Vehículo: *{state}*"

    def _cmd_trips(self) -> str:
        text = self.logger.format_recent(limit=5)
        if text.startswith("No completed"):
            return "📭 Aún no hay viajes completados."
        # polish header
        return "🗺️ *Últimos viajes*\n" + "\n".join(text.splitlines()[1:])

    def _cmd_active_trip(self) -> str:
        active = self.logger.get_active_trip()
        if not active:
            mon_id = self.monitor.active_trip_id if self.monitor else None
            if mon_id:
                return f"🚗 Monitor reporta viaje *#{mon_id}* (sincronizando DB…)"
            return "🅿️ No hay viaje activo ahora."
        odo = active.get("start_odometer_km")
        return (
            f"🚗 *Viaje activo #{active['id']}*\n"
            f"• Inicio: {active.get('start_time')}\n"
            f"• Odómetro inicio: {odo} km\n"
            f"• Batería inicio: {active.get('battery_start')}%\n"
            f"• Contexto: {active.get('charge_context') or 'home'}"
        )

    def _cmd_monitor(self) -> str:
        if not self.monitor:
            return "📡 TripMonitor no está conectado a este handler."
        s = self.monitor.status_dict()
        return (
            f"📡 *TripMonitor*\n"
            f"• Running: *{s['running']}*\n"
            f"• Modo: {'demo' if s['demo'] else 'live'}\n"
            f"• Poll: cada {s['poll_seconds']}s\n"
            f"• Viaje activo: {s['active_trip_id'] or 'ninguno'}\n"
            f"• Último estado: {s['last_drive_state'] or '—'} "
            f"(bat {s['last_battery'] if s['last_battery'] is not None else '—'}%)"
        )

    @staticmethod
    def _format_summary(s: Dict[str, Any], label: str) -> str:
        eff = s.get("avg_efficiency_wh_per_km")
        eff_s = f"\n• Eficiencia media: {eff} Wh/km" if eff is not None else ""
        return (
            f"📊 *Resumen {label}*\n"
            f"• Viajes: *{s['trip_count']}*\n"
            f"• Distancia: *{s['total_distance_km']}* km\n"
            f"• Energía: *{s['total_energy_kwh']}* kWh\n"
            f"• Costo est.: *COP {s['total_cost_cop']}*{eff_s}"
        )

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    async def notify_family(self, text: str) -> bool:
        if not self.notify:
            return False
        ok = await self.telegram.broadcast(text)
        if self.whatsapp is not None:
            try:
                await self.whatsapp.send_message(text)
            except Exception:
                pass
        return ok

    async def notify_trip_complete(self, summary: Dict[str, Any]) -> str:
        """Format and send a trip-complete notification."""
        if summary.get("status") == "cancelled":
            text = (
                f"↩️ Viaje #{summary.get('id')} cancelado "
                f"({summary.get('distance_km', 0)} km — muy corto)"
            )
        else:
            eff = summary.get("efficiency_wh_per_km")
            eff_s = f"\n• Eficiencia: {eff} Wh/km" if eff is not None else ""
            text = (
                f"✅ *Viaje #{summary.get('id')} terminado*\n"
                f"• Distancia: *{summary.get('distance_km')}* km\n"
                f"• Batería: {summary.get('battery_start')}% → "
                f"{summary.get('battery_end')}% "
                f"({summary.get('battery_used_pct')}%)\n"
                f"• Energía: {summary.get('energy_used_kwh')} kWh{eff_s}\n"
                f"• Costo est.: *COP {summary.get('cost_cop')}* "
                f"({summary.get('charge_context', 'home')})"
            )
        await self.notify_family(text)
        return text

    async def check_charge_reminders(
        self,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Inspect vehicle snapshot and send charge reminders if needed."""
        if snapshot is None:
            try:
                snapshot = await self.tesla.get_vehicle_data(wake=False)
            except TeslaAPIError:
                return []

        notices: List[str] = []
        now = time.time()
        cooldown = config.CHARGE_REMINDER_COOLDOWN_MIN * 60

        level = snapshot.get("battery_level")
        try:
            level_f = float(level) if level is not None else None
        except (TypeError, ValueError):
            level_f = None

        charging_state = str(snapshot.get("charging_state") or "")
        charging_l = charging_state.lower()
        is_charging = charging_l in {"charging", "starting", "connected"}
        is_complete = charging_l in {"complete", "completed"}
        charge_limit = snapshot.get("charge_limit_soc") or config.CHARGE_REMINDER_TARGET

        if level_f is not None and level_f <= config.CHARGE_LOW_PERCENT and not is_charging:
            if (
                not self._low_battery_active
                or (now - self._last_low_battery_notice) >= cooldown
            ):
                target = config.CHARGE_REMINDER_TARGET
                text = (
                    f"🔋 *Batería baja: {level_f:.0f}%*\n"
                    f"Conecta el cargador. Sugerencia: `carga {target}`"
                )
                await self.notify_family(text)
                notices.append(text)
                self._last_low_battery_notice = now
                self._low_battery_active = True
        elif level_f is not None and level_f > config.CHARGE_LOW_PERCENT:
            self._low_battery_active = False

        reached_limit = (
            level_f is not None
            and charge_limit is not None
            and level_f >= float(charge_limit) - 0.5
            and (is_complete or is_charging)
        )
        transition_complete = self._was_charging and (
            is_complete or charging_l in {"disconnected", "stopped"}
        )

        if reached_limit or transition_complete:
            if (now - self._last_charge_complete_notice) >= cooldown:
                if is_complete or reached_limit:
                    text = (
                        f"🔌 *Carga lista: {level_f:.0f}%* "
                        f"(límite {charge_limit}%)\n"
                        f"Puedes desconectar el cable."
                    )
                else:
                    text = (
                        f"🔌 Carga detenida en {level_f:.0f}% "
                        f"(estado: {charging_state})"
                    )
                await self.notify_family(text)
                notices.append(text)
                self._last_charge_complete_notice = now

        self._was_charging = is_charging or is_complete
        return notices

    async def on_trip_end(self, summary: Dict[str, Any]) -> None:
        """Callback for TripMonitor.on_trip_end (trip notification only).

        Charge reminders run via on_snapshot on the same poll to avoid duplicates.
        """
        await self.notify_trip_complete(summary)

    async def on_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Callback for each TripMonitor poll — charge reminders."""
        await self.check_charge_reminders(snapshot)
