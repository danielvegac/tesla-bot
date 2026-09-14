"""Home geofence from the driveway pin."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

import places

HOME_RADIUS_M = 80.0


def _m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return places._haversine_km(lat1, lon1, lat2, lon2) * 1000.0


def distance_to_home_m(lat: float, lon: float) -> float:
    return _m(lat, lon, places.HOME["lat"], places.HOME["lon"])


def at_home(lat: Optional[float], lon: Optional[float], radius_m: float = HOME_RADIUS_M) -> Optional[bool]:
    if lat is None or lon is None:
        return None
    return distance_to_home_m(float(lat), float(lon)) <= radius_m


def where_line(snap: Dict[str, Any], *, spanish: bool = True) -> str:
    lat, lon = snap.get("latitude"), snap.get("longitude")
    parked = str(snap.get("drive_state_label") or snap.get("shift_state") or "").lower() in {
        "parked",
        "p",
        "park",
    }
    home = at_home(lat if lat is None else float(lat), lon if lon is None else float(lon))
    if home is True:
        if spanish:
            return "Estoy parqueado en casa." if parked or True else "Estoy en casa."
        return "I'm parked at home."
    if home is None:
        if spanish:
            return "No tengo GPS ahora mismo."
        return "I don't have GPS right now."
    meters = int(distance_to_home_m(float(lat), float(lon)))
    if spanish:
        return f"No estoy en casa (a unos {meters} m). GPS {float(lat):.5f}, {float(lon):.5f}."
    return f"Not at home (~{meters} m away)."
