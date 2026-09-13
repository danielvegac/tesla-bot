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
)


def is_confirm(text: str) -> bool:
    t = fold(text).replace(",", " ")
    return bool(CONFIRM_RE.search(t)) or "mandalo" in t or "envialo" in t or "send it" in t


def is_deny(text: str) -> bool:
    return bool(DENY_RE.search(fold(text)))


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
    if "unicentro" in t:
        return "Unicentro"
    if "el rancho" in t or "club campestre" in t:
        return "Club Campestre El Rancho"
    return None
