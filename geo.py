"""Home and work geofences from captured GPS pins."""

from __future__ import annotations

from typing import Any, Dict, Optional

import places

HOME_RADIUS_M = 80.0
WORK_RADIUS_M = 80.0


def _m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return places._haversine_km(lat1, lon1, lat2, lon2) * 1000.0


def distance_to_home_m(lat: float, lon: float) -> float:
    return _m(lat, lon, places.HOME["lat"], places.HOME["lon"])


def at_home(lat: Optional[float], lon: Optional[float], radius_m: float = HOME_RADIUS_M) -> Optional[bool]:
    if lat is None or lon is None:
        return None
    return distance_to_home_m(float(lat), float(lon)) <= radius_m


def work_configured() -> bool:
    return places.WORK is not None


def distance_to_work_m(lat: float, lon: float) -> Optional[float]:
    work = places.WORK
    if work is None:
        return None
    return _m(lat, lon, work["lat"], work["lon"])


def at_work(lat: Optional[float], lon: Optional[float], radius_m: float = WORK_RADIUS_M) -> Optional[bool]:
    if lat is None or lon is None:
        return None
    dist = distance_to_work_m(float(lat), float(lon))
    if dist is None:
        return None
    return dist <= radius_m


def where_line(snap: Dict[str, Any], *, spanish: bool = True) -> str:
    lat, lon = snap.get("latitude"), snap.get("longitude")
    parked = str(snap.get("drive_state_label") or snap.get("shift_state") or "").lower() in {
        "parked",
        "p",
        "park",
    }
    if lat is None or lon is None:
        if spanish:
            return "No tengo GPS ahora mismo."
        return "I don't have GPS right now."
    lat_f, lon_f = float(lat), float(lon)
    if at_home(lat_f, lon_f) is True:
        if spanish:
            return "Estoy parqueado en casa." if parked else "Estoy en casa."
        return "I'm parked at home." if parked else "I'm at home."
    if at_work(lat_f, lon_f) is True:
        label = (places.WORK or {}).get("short") or "oficina"
        if spanish:
            return f"Estoy parqueado en {label}." if parked else f"Estoy en {label}."
        return f"I'm parked at {label}." if parked else f"I'm at {label}."
    meters = int(distance_to_home_m(lat_f, lon_f))
    if spanish:
        return f"No estoy en casa (a unos {meters} m). GPS {lat_f:.5f}, {lon_f:.5f}."
    return f"Not at home (~{meters} m away)."
