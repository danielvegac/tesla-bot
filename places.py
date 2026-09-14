"""Resolve family place names and estimate driving distance."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import urllib.parse
import urllib.request
import json
import math

USER_AGENT = "TeslaFamiliaBot/1.0 (github.com/danielvegac/tesla-bot)"

# Driveway captured 2026-09-13 from live Fleet GPS while parked at home.
HOME = {
    "query": "casa",
    "search": "home driveway",
    "label": "Casa",
    "short": "Casa",
    "lat": 4.700454,
    "lon": -74.027738,
}

PLACE_ALIASES = {
    "unicentro": "Unicentro Bogotá, Colombia",
    "unicentro bogota": "Unicentro Bogotá, Colombia",
    "unicentro bogotá": "Unicentro Bogotá, Colombia",
    "el rancho": "Club Campestre El Rancho, Bogotá, Colombia",
    "club campestre el rancho": "Club Campestre El Rancho, Bogotá, Colombia",
    "rancho": "Club Campestre El Rancho, Bogotá, Colombia",
}

SHORT_NAMES = {
    "unicentro": "Unicentro",
    "unicentro bogota": "Unicentro",
    "unicentro bogotá": "Unicentro",
    "el rancho": "El Rancho",
    "club campestre el rancho": "El Rancho",
    "rancho": "El Rancho",
    "casa": "Casa",
    "home": "Casa",
}


def short_label(place: Dict[str, Any]) -> str:
    q = str(place.get("query") or "").strip().lower()
    if q in SHORT_NAMES:
        return SHORT_NAMES[q]
    label = str(place.get("label") or place.get("query") or "").strip()
    return label.split(",")[0].strip() or label


def _http_json(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def resolve_place(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return None
    key = q.lower()
    if key in {"casa", "home", "a casa", "mi casa"}:
        return dict(HOME)
    search = PLACE_ALIASES.get(key, q if "," in q else f"{q}, Bogotá, Colombia")
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode({"q": search, "format": "json", "limit": 1})
    )
    try:
        hits = _http_json(url) or []
    except Exception as exc:
        print(f"[places] nominatim failed: {exc}")
        return None
    if not hits:
        print(f"[places] no pin for {q!r} (search={search!r})")
        return None
    hit = hits[0]
    try:
        place = {
            "query": q,
            "search": search,
            "label": hit.get("display_name") or search,
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
        }
        place["short"] = short_label(place)
        return place
    except (KeyError, TypeError, ValueError):
        return None


def driving_km(origin: Tuple[float, float], dest: Tuple[float, float]) -> Optional[float]:
    o_lat, o_lon = origin
    d_lat, d_lon = dest
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{o_lon},{o_lat};{d_lon},{d_lat}?overview=false"
    )
    try:
        data = _http_json(url)
    except Exception:
        return _haversine_km(o_lat, o_lon, d_lat, d_lon)
    routes = data.get("routes") or []
    if not routes:
        return _haversine_km(o_lat, o_lon, d_lat, d_lon)
    meters = routes[0].get("distance") or 0
    return round(float(meters) / 1000.0, 2)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


def estimate_arrival_soc(
    battery_level: Optional[float],
    battery_range_km: Optional[float],
    route_km: Optional[float],
    buffer_frac: float = 0.12,
) -> Dict[str, Any]:
    if battery_level is None or battery_range_km is None or route_km is None:
        return {"ok": False, "reason": "missing battery, range, or route_km"}
    if battery_range_km <= 0:
        return {"ok": False, "reason": "range is zero"}
    used_frac = route_km / float(battery_range_km)
    arrival = float(battery_level) * (1.0 - used_frac)
    arrival_buffered = arrival - (float(battery_level) * used_frac * buffer_frac)
    comfortable = arrival_buffered >= 15
    tight = 8 <= arrival_buffered < 15
    return {
        "ok": True,
        "route_km": route_km,
        "arrival_soc_pct": round(max(arrival, 0.0), 1),
        "arrival_soc_buffered_pct": round(max(arrival_buffered, 0.0), 1),
        "comfortable": comfortable,
        "tight": tight,
        "note": "Estimate from Tesla rated range + driving distance. Not Tesla in-car trip planner.",
    }
