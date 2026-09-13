"""Deterministic family intents. Used by the router and by offline evals."""

from __future__ import annotations

import re
import unicodedata


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
    }:
        return True
    words = t.replace("?", " ").replace("!", " ").replace(",", " ").split()
    if "wake" in words and "awake" not in words:
        return True
    if words and words[0] in {"despierta", "despertar", "despiertate"}:
        return True
    if "despiert" in t and any(w in t for w in ("por favor", "tesla", "carro", "auto")):
        return True
    return False


CONFIRM_RE = re.compile(
    r"^(si|s[ií]|yes|ok|okay|dale|claro|mando|mandalo|envialo|send it|send)\b",
    re.I,
)
DENY_RE = re.compile(r"^(no|nop|cancel|cancela|cancelar|stop)\b", re.I)


def is_confirm(text: str) -> bool:
    t = fold(text).replace(",", " ")
    return bool(CONFIRM_RE.search(t)) or "mandalo" in t or "envialo" in t or "send it" in t


def is_deny(text: str) -> bool:
    return bool(DENY_RE.search(fold(text)))
