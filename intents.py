"""Deterministic family intents. Used by the router and by offline evals."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").strip().lower()


def is_wake(text: str) -> bool:
    t = fold(text)
    if not t:
        return False
    if t in {
        "wake",
        "wakeup",
        "wake up",
        "online",
        "despertar",
        "despierta",
        "despiertate",
        "despertarte",
    }:
        return True
    words = t.replace("?", " ").replace("!", " ").replace(",", " ").split()
    if "wake" in words and "awake" not in words:
        return True
    if re.search(r"\bdespertar(?:te)?\b|\bdespierta(?:te)?\b", t):
        return True
    return False


CONFIRM_RE = re.compile(
    r"^(si|s[ií]|yes|ok|okay|dale|claro|mando|mandalo|envialo|send it|send)\b",
    re.I,
)
DENY_RE = re.compile(r"^(no|nop|cancel|cancela|cancelar|stop)\b", re.I)
NAV_PREFIX = (
    "marca el destino a ",
    "marca destino a ",
    "marca el destino ",
    "marca el curso para ",
    "marca el curso a ",
    "marca curso para ",
    "marca el curso ",
    "curso para ",
    "envia el destino a ",
    "enviar destino a ",
    "ir a ",
    "navegar a ",
    "go to ",
    "destino a ",
    "mandalo a ",
    "manda a ",
    "llevame a ",
    "llévame a ",
)


def is_confirm(text: str) -> bool:
    t = fold(text).replace(",", " ")
    return bool(CONFIRM_RE.search(t)) or "mandalo" in t or "envialo" in t or "send it" in t


def is_deny(text: str) -> bool:
    return bool(DENY_RE.search(fold(text)))


def is_flash(text: str) -> bool:
    t = fold(text)
    if not t:
        return False
    if t in {
        "flash",
        "luces",
        "lights",
        "flash lights",
        "destellar",
        "parpadear",
        "parpadea",
        "destella",
    }:
        return True
    if re.search(r"\b(flash|destell|parpade)\b", t):
        return True
    if "luces" in t and any(w in t for w in ("prende", "enciende", "flash", "parpade", "destell")):
        return True
    return False


def is_honk(text: str) -> bool:
    t = fold(text)
    if t in {"honk", "claxon", "bocina", "pito", "horn", "beep", "corneta"}:
        return True
    return bool(re.search(r"\b(honk|claxon|bocina|pito|horn|beep|corneta)\b", t))


def is_unlock(text: str) -> bool:
    t = fold(text)
    if t in {
        "unlock",
        "desbloquear",
        "abrir",
        "abierto",
        "abre",
        "unlock doors",
        "abrir puertas",
        "abre las puertas",
        "open doors",
    }:
        return True
    return bool(re.search(r"\b(unlock|desbloquear)\b", t) or re.search(r"\babre(?:r)? las puertas\b", t))


def is_lock(text: str) -> bool:
    t = fold(text)
    if is_unlock(text):
        return False
    if t in {
        "lock",
        "bloquear",
        "cerrar",
        "cerrado",
        "cierra",
        "lock doors",
        "cerrar puertas",
        "cierra las puertas",
        "block doors",
        "block the doors",
        "bloquea las puertas",
        "bloquea puertas",
    }:
        return True
    return bool(
        re.search(r"\b(lock|bloquear|bloquea)\b", t)
        or re.search(r"\bcierr[ae](?:r)? las puertas\b", t)
        or "block door" in t
    )


def is_climate_off(text: str) -> bool:
    t = fold(text)
    if t in {
        "apagar clima",
        "apaga el clima",
        "apaga el aire",
        "apagar aire",
        "apagar ac",
        "clima off",
        "climate off",
        "stop climate",
        "stop precondition",
        "aire off",
        "ac off",
    }:
        return True
    return bool(
        re.search(r"\b(apaga(?:r)?|off|stop)\b", t)
        and re.search(r"\b(clima|aire|ac|hvac|climate|precondition)\b", t)
    )


def is_climate_on(text: str) -> bool:
    t = fold(text)
    if is_climate_off(text) or climate_temp(text) is not None:
        return False
    if t in {
        "clima",
        "aire",
        "ac",
        "a/c",
        "precondition",
        "precondicion",
        "climatizar",
        "climate on",
        "prende el clima",
        "prende el aire",
        "enciende el clima",
        "enciende el aire",
    }:
        return True
    return bool(
        re.search(r"\b(prende|enciende|on|start)\b", t)
        and re.search(r"\b(clima|aire|ac|hvac|climate)\b", t)
    )


def climate_temp(text: str) -> Optional[float]:
    t = fold(text)
    if not re.search(r"\b(clima|aire|ac|temp|grados|degrees|celsius)\b", t):
        return None
    match = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*(?:c|f|grados|degrees)?", t)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    if 15 <= value <= 28:
        return value
    return None


def is_day_digest(text: str) -> bool:
    t = fold(text)
    return t in {
        "resumen",
        "summary",
        "hoy",
        "today",
        "resumen hoy",
        "viajes hoy",
        "trips today",
        "totales",
        "digest",
    }


def navigation_destination(text: str) -> Optional[str]:
    raw = (text or "").strip()
    t = fold(raw)
    if not t:
        return None
    for prefix in NAV_PREFIX:
        idx = t.find(prefix)
        if idx >= 0:
            dest = raw[idx + len(prefix) :].strip(" .,;?")
            return dest or None
    if t in {"casa", "home", "a casa", "ir casa"}:
        return "casa"
    if t in {"oficina", "trabajo", "work", "office", "jeeves"}:
        return "oficina"
    if "unicentro" in t:
        return "Unicentro"
    if "el rancho" in t or "club campestre" in t:
        return "Club Campestre El Rancho"
    if re.search(r"\bcasa\b", t) and any(w in t for w in ("marca", "ir", "curso", "destino", "home", "llev")):
        return "casa"
    if re.search(r"\b(oficina|trabajo|jeeves)\b", t) and any(
        w in t for w in ("marca", "ir", "curso", "destino", "llev", "go")
    ):
        return "oficina"
    return None
