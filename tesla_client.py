"""Tesla Fleet API client with config-based auth and demo fallback."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import config

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


MILES_TO_KM = 1.60934
KM_TO_MILES = 0.621371


class TeslaAPIError(Exception):
    """Raised when the Tesla Fleet API returns an error or is misconfigured."""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TeslaClient:
    """Async client for Tesla Fleet API vehicle data and commands.

    When DEMO_MODE is on or TESLA_ACCESS_TOKEN is a placeholder, all methods
    use in-memory mock data so the bot still works offline for development.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        vin: Optional[str] = None,
        base_url: Optional[str] = None,
        demo: Optional[bool] = None,
        timeout: float = 30.0,
    ):
        self.access_token = access_token if access_token is not None else config.TESLA_ACCESS_TOKEN
        self.vin = (vin if vin is not None else config.TESLA_VIN).upper()
        self.base_url = (base_url or config.get_tesla_base_url()).rstrip("/")
        self.demo = config.is_demo_mode() if demo is None else demo
        self.timeout = timeout
        self._vehicle_id: Optional[int] = None
        self._client: Optional[Any] = None

        # Demo-state (mutated by mock commands / data reads)
        self._demo_battery = 65
        self._demo_odometer_km = 12345.6
        self._demo_shift = "P"
        self._demo_speed = 0.0
        self._demo_charge_limit = 80
        self._demo_lat = 4.6097
        self._demo_lon = -74.0817
        self._demo_locked = True
        self._demo_climate_on = False

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "TeslaFamiliaBot/1.0",
        }

    async def _get_http(self) -> Any:
        if httpx is None:
            raise TeslaAPIError(
                "httpx is not installed. Run: pip install -r requirements.txt"
            )
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        wake_if_needed: bool = False,
    ) -> Any:
        if self.demo:
            raise TeslaAPIError("Internal: _request called in demo mode")

        client = await self._get_http()
        url = path if path.startswith("http") else path
        try:
            response = await client.request(method, url, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise TeslaAPIError(f"Tesla API timeout on {method} {path}") from exc
        except httpx.RequestError as exc:
            raise TeslaAPIError(f"Tesla API network error: {exc}") from exc

        if response.status_code == 401:
            raise TeslaAPIError(
                "Unauthorized (401). Check TESLA_ACCESS_TOKEN — it may be expired "
                "or missing Fleet API scopes.",
                status_code=401,
                body=_safe_json(response),
            )
        if response.status_code == 403:
            raise TeslaAPIError(
                "Forbidden (403). Token may lack vehicle_device_data / vehicle_cmds "
                "scopes, or the vehicle is not linked to this account.",
                status_code=403,
                body=_safe_json(response),
            )
        if response.status_code == 408:
            if wake_if_needed:
                await self.wake_up()
                return await self._request(
                    method, path, json=json, params=params, wake_if_needed=False
                )
            raise TeslaAPIError(
                "Vehicle is asleep (408). Call wake_up() first.",
                status_code=408,
                body=_safe_json(response),
            )
        if response.status_code >= 400:
            raise TeslaAPIError(
                f"Tesla API error {response.status_code} on {method} {path}: "
                f"{response.text[:400]}",
                status_code=response.status_code,
                body=_safe_json(response),
            )

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    # ------------------------------------------------------------------
    # Vehicle identity
    # ------------------------------------------------------------------

    async def list_vehicles(self) -> list:
        if self.demo:
            return [
                {
                    "id": 1,
                    "vehicle_id": 1,
                    "vin": self.vin if config.has_real_vin() else "DEMO0000000000000",
                    "display_name": "Familia Demo",
                    "state": "online",
                }
            ]
        data = await self._request("GET", "/api/1/vehicles")
        return data.get("response") or []

    async def _resolve_vehicle_id(self) -> int:
        if self._vehicle_id is not None:
            return self._vehicle_id

        vehicles = await self.list_vehicles()
        if not vehicles:
            raise TeslaAPIError("No vehicles returned for this account/token.")

        if config.has_real_vin() and not self.demo:
            for v in vehicles:
                if str(v.get("vin", "")).upper() == self.vin:
                    self._vehicle_id = int(v["id"])
                    return self._vehicle_id
            known = ", ".join(str(v.get("vin")) for v in vehicles)
            raise TeslaAPIError(
                f"VIN {self.vin} not found on this account. Known VINs: {known}"
            )

        # Demo or no VIN configured: use first vehicle
        self._vehicle_id = int(vehicles[0]["id"])
        if vehicles[0].get("vin"):
            self.vin = str(vehicles[0]["vin"]).upper()
        return self._vehicle_id

    # ------------------------------------------------------------------
    # Wake / data
    # ------------------------------------------------------------------

    async def wake_up(self, max_wait_s: float = 45.0, poll_s: float = 2.5) -> Dict[str, Any]:
        """Wake the vehicle and wait until it reports online (or demo no-op)."""
        if self.demo:
            print("☀️ [demo] Vehicle already online")
            return {"state": "online", "demo": True}

        vehicle_id = await self._resolve_vehicle_id()
        data = await self._request("POST", f"/api/1/vehicles/{vehicle_id}/wake_up")
        state = (data.get("response") or {}).get("state", "unknown")
        deadline = time.monotonic() + max_wait_s

        while state != "online" and time.monotonic() < deadline:
            await asyncio.sleep(poll_s)
            vehicles = await self.list_vehicles()
            match = next(
                (v for v in vehicles if int(v.get("id", -1)) == vehicle_id),
                None,
            )
            if match:
                state = match.get("state", state)
            if state == "online":
                break

        print(f"☀️ Vehicle wake state: {state}")
        return data.get("response") or {"state": state}

    async def get_vehicle_data(self, wake: bool = True) -> Dict[str, Any]:
        """Fetch and normalize vehicle_data for trip logging / status."""
        if self.demo:
            return self._demo_snapshot()

        vehicle_id = await self._resolve_vehicle_id()
        try:
            data = await self._request(
                "GET",
                f"/api/1/vehicles/{vehicle_id}/vehicle_data",
                wake_if_needed=wake,
            )
        except TeslaAPIError as exc:
            if wake and exc.status_code == 408:
                await self.wake_up()
                data = await self._request(
                    "GET",
                    f"/api/1/vehicles/{vehicle_id}/vehicle_data",
                    wake_if_needed=False,
                )
            else:
                raise

        response = data.get("response") or data
        return self._normalize_vehicle_data(response)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _command(self, name: str, body: Optional[dict] = None) -> Dict[str, Any]:
        vehicle_id = await self._resolve_vehicle_id()
        path = f"/api/1/vehicles/{vehicle_id}/command/{name}"
        try:
            data = await self._request("POST", path, json=body or {}, wake_if_needed=True)
        except TeslaAPIError as exc:
            if exc.status_code == 408:
                await self.wake_up()
                data = await self._request("POST", path, json=body or {}, wake_if_needed=False)
            else:
                raise
        return data

    async def set_charge_limit(self, percent: int) -> str:
        percent = max(50, min(100, int(percent)))
        if self.demo:
            self._demo_charge_limit = percent
            return f"charge_limit:{percent}:demo"
        await self._command("set_charge_limit", {"percent": percent})
        return f"charge_limit:{percent}"

    async def precondition(self, minutes: int = 20) -> str:
        # Fleet API starts climate; duration is app-side preference only.
        if self.demo:
            self._demo_climate_on = True
            return f"precondition_start:{minutes}:demo"
        await self._command("auto_conditioning_start")
        return f"precondition_start:{minutes}"

    async def stop_precondition(self) -> str:
        if self.demo:
            self._demo_climate_on = False
            return "precondition_stop:demo"
        await self._command("auto_conditioning_stop")
        return "precondition_stop"

    async def send_navigation(self, destination: str) -> str:
        destination = (destination or "").strip()
        if not destination:
            raise TeslaAPIError("Navigation destination is empty")

        if self.demo:
            return f"navigate:{destination}:demo"

        # share / navigation_request payload shape used by Fleet / owner APIs
        body = {
            "type": "share_ext_content_raw",
            "value": {
                "android.intent.extra.TEXT": destination,
            },
            "locale": "en-US",
            "timestamp_ms": str(int(time.time() * 1000)),
        }
        try:
            await self._command("navigation_request", body)
        except TeslaAPIError:
            # Fallback alternate endpoint name some accounts still accept
            await self._command(
                "share",
                {
                    "type": "share_ext_content_raw",
                    "value": {"android.intent.extra.TEXT": destination},
                    "locale": "en-US",
                    "timestamp_ms": str(int(time.time() * 1000)),
                },
            )
        return f"navigate:{destination}"

    async def lock_doors(self, lock: bool = True) -> str:
        if self.demo:
            self._demo_locked = lock
            return f"doors:{'locked' if lock else 'unlocked'}:demo"
        await self._command("door_lock" if lock else "door_unlock")
        return f"doors:{'locked' if lock else 'unlocked'}"

    async def honk_horn(self) -> str:
        if self.demo:
            return "honk:demo"
        await self._command("honk_horn")
        return "honk"

    async def flash_lights(self) -> str:
        if self.demo:
            return "flash:demo"
        await self._command("flash_lights")
        return "flash"

    # ------------------------------------------------------------------
    # Normalization / demo snapshot
    # ------------------------------------------------------------------

    def _normalize_vehicle_data(self, response: Dict[str, Any]) -> Dict[str, Any]:
        charge = response.get("charge_state") or {}
        drive = response.get("drive_state") or {}
        climate = response.get("climate_state") or {}
        vehicle_state = response.get("vehicle_state") or {}
        gui = response.get("gui_settings") or {}

        distance_unit = (gui.get("gui_distance_units") or "km/hr").lower()
        use_miles = "mi" in distance_unit

        def to_km(value: Optional[float]) -> Optional[float]:
            if value is None:
                return None
            return float(value) * MILES_TO_KM if use_miles else float(value)

        odometer_raw = vehicle_state.get("odometer")
        speed_raw = drive.get("speed")
        battery_range_raw = charge.get("battery_range") or charge.get("ideal_battery_range")

        shift = drive.get("shift_state")
        speed_kmh = to_km(speed_raw) if speed_raw is not None else None
        # When parked, API often returns null speed / shift
        if shift is None and (speed_kmh is None or speed_kmh == 0):
            inferred_state = "parked"
        elif shift == "P":
            inferred_state = "parked"
        else:
            inferred_state = "driving"

        snapshot = {
            "vin": response.get("vin") or self.vin,
            "display_name": response.get("display_name"),
            "state": response.get("state") or "online",
            "drive_state_label": inferred_state,
            "shift_state": shift,
            "speed_kmh": speed_kmh,
            "battery_level": charge.get("battery_level"),
            "battery_range_km": to_km(battery_range_raw),
            "charge_limit_soc": charge.get("charge_limit_soc"),
            "charging_state": charge.get("charging_state"),
            "charge_energy_added": charge.get("charge_energy_added"),
            "charger_power": charge.get("charger_power"),
            "odometer_km": to_km(odometer_raw) if odometer_raw is not None else None,
            "latitude": drive.get("latitude"),
            "longitude": drive.get("longitude"),
            "heading": drive.get("heading"),
            "inside_temp": climate.get("inside_temp"),
            "outside_temp": climate.get("outside_temp"),
            "is_climate_on": climate.get("is_climate_on"),
            "locked": vehicle_state.get("locked"),
            "car_version": vehicle_state.get("car_version"),
            "gui_distance_units": gui.get("gui_distance_units"),
            "timestamp": response.get("vehicle_state", {}).get("timestamp")
            or charge.get("timestamp"),
            "demo": False,
        }
        return snapshot

    def _demo_snapshot(self) -> Dict[str, Any]:
        # Light drift so repeated polls look alive
        if self._demo_shift in {"D", "R", "N"} and self._demo_speed > 0:
            self._demo_odometer_km += self._demo_speed * (config.TRIP_POLL_SECONDS / 3600.0)
            self._demo_battery = max(5, self._demo_battery - 0.02)

        return {
            "vin": self.vin if config.has_real_vin() else "DEMO0000000000000",
            "display_name": "Familia Demo",
            "state": "online",
            "drive_state_label": "parked" if self._demo_shift == "P" else "driving",
            "shift_state": self._demo_shift,
            "speed_kmh": self._demo_speed,
            "battery_level": round(self._demo_battery, 1),
            "battery_range_km": round(self._demo_battery * 4.2, 1),
            "charge_limit_soc": self._demo_charge_limit,
            "charging_state": "Disconnected",
            "charge_energy_added": 0.0,
            "charger_power": 0,
            "odometer_km": round(self._demo_odometer_km, 2),
            "latitude": self._demo_lat,
            "longitude": self._demo_lon,
            "heading": 90,
            "inside_temp": 22.0 if self._demo_climate_on else 28.0,
            "outside_temp": 26.0,
            "is_climate_on": self._demo_climate_on,
            "locked": self._demo_locked,
            "car_version": "demo-1.0",
            "gui_distance_units": "km/hr",
            "timestamp": int(time.time() * 1000),
            "demo": True,
        }

    # Demo helpers for future trip-monitor tests
    def demo_set_driving(self, speed_kmh: float = 40.0) -> None:
        self._demo_shift = "D"
        self._demo_speed = speed_kmh

    def demo_set_parked(self) -> None:
        self._demo_shift = "P"
        self._demo_speed = 0.0


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return getattr(response, "text", None)


async def _smoke_test() -> None:
    """Quick manual check: python -m tesla_client"""
    client = TeslaClient()
    mode = "DEMO" if client.demo else "LIVE"
    print(f"TeslaClient mode={mode}")
    print(f"  base_url={client.base_url}")
    print(f"  vin={client.vin}")
    print(f"  token_set={bool(client.access_token) and client.access_token != 'your_token_here'}")

    try:
        vehicles = await client.list_vehicles()
        print(f"  vehicles={len(vehicles)}")
        data = await client.get_vehicle_data()
        print("  snapshot:")
        for key in (
            "vin",
            "state",
            "drive_state_label",
            "battery_level",
            "battery_range_km",
            "odometer_km",
            "shift_state",
            "charging_state",
            "demo",
        ):
            print(f"    {key}: {data.get(key)}")
        print("  set_charge_limit:", await client.set_charge_limit(80))
        print("  precondition:", await client.precondition())
        print("  lock:", await client.lock_doors(True))
        print("  nav:", await client.send_navigation("Unicentro"))
        print("  honk:", await client.honk_horn())
        print("  flash:", await client.flash_lights())
    except TeslaAPIError as exc:
        print(f"  API error: {exc}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(_smoke_test())
