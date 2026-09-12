"""Runtime configuration for Tesla Familia Bot.

Values load from environment variables (and optional .env), with safe defaults
for local demo use. Do not commit real secrets.
"""

from __future__ import annotations

import os
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv optional until installed


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_recipients(raw: str) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


# --- Tesla Fleet API ---
TESLA_ACCESS_TOKEN = _env("TESLA_ACCESS_TOKEN", "your_token_here")
TESLA_REFRESH_TOKEN = _env("TESLA_REFRESH_TOKEN", "")
TESLA_VIN = _env("TESLA_VIN") or _env("VIN", "your_vin_here")
VIN = TESLA_VIN

TESLA_REGION = _env("TESLA_REGION", "na").lower()
TESLA_BASE_URL = _env("TESLA_BASE_URL", "")
TESLA_COMMAND_BASE_URL = _env("TESLA_COMMAND_BASE_URL", "")
TESLA_HTTP_VERIFY = _env_bool("TESLA_HTTP_VERIFY", True)
TESLA_COMMAND_HTTP_VERIFY = _env_bool(
    "TESLA_COMMAND_HTTP_VERIFY",
    False if "127.0.0.1" in TESLA_COMMAND_BASE_URL or "localhost" in TESLA_COMMAND_BASE_URL else True,
)

TESLA_REGION_BASE_URLS = {
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}


def get_tesla_base_url() -> str:
    if TESLA_BASE_URL:
        return TESLA_BASE_URL.rstrip("/")
    return TESLA_REGION_BASE_URLS.get(TESLA_REGION, TESLA_REGION_BASE_URLS["na"])


def get_tesla_command_base_url() -> str:
    if TESLA_COMMAND_BASE_URL:
        return TESLA_COMMAND_BASE_URL.rstrip("/")
    return get_tesla_base_url()


DEMO_MODE = _env_bool("DEMO_MODE", False)

_PLACEHOLDER_TOKENS = {"", "your_token_here", "changeme", "xxx"}
_PLACEHOLDER_VINS = {"", "your_vin_here", "changeme", "xxx"}


def is_demo_mode() -> bool:
    if DEMO_MODE:
        return True
    if TESLA_ACCESS_TOKEN.lower() in _PLACEHOLDER_TOKENS:
        return True
    return False


def has_real_vin() -> bool:
    return TESLA_VIN.lower() not in _PLACEHOLDER_VINS


HOME_ELECTRICITY_RATE = _env_float("HOME_ELECTRICITY_RATE", 650.0)
SUPERCHARGER_RATE = _env_float("SUPERCHARGER_RATE", 1300.0)
BATTERY_CAPACITY_KWH = _env_float("BATTERY_CAPACITY_KWH", 75.0)

TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = _parse_recipients(_env("TELEGRAM_CHAT_IDS", ""))

WHATSAPP_TOKEN = _env("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = _env("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = _env("WHATSAPP_VERIFY_TOKEN", "tesla-familia-verify")
WHATSAPP_RECIPIENTS = _parse_recipients(
    _env("WHATSAPP_RECIPIENTS", "+57YOUR_NUMBER")
)

TRIP_POLL_SECONDS = _env_int("TRIP_POLL_SECONDS", 45)

CHARGE_LOW_PERCENT = _env_int("CHARGE_LOW_PERCENT", 20)
CHARGE_REMINDER_TARGET = _env_int("CHARGE_REMINDER_TARGET", 80)
CHARGE_REMINDER_COOLDOWN_MIN = _env_int("CHARGE_REMINDER_COOLDOWN_MIN", 60)

# --- LLM agent (OpenRouter / xAI / Ollama) ---
LLM_BACKEND = _env("LLM_BACKEND", "openrouter").lower()
LLM_MODEL = _env("LLM_MODEL", "qwen/qwen3.7-flash")
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY", "")
XAI_API_KEY = _env("XAI_API_KEY", "")
OLLAMA_HOST = _env("OLLAMA_HOST", "http://127.0.0.1:11434/v1")

_LLM_BASES = {
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "ollama": OLLAMA_HOST,
}


def llm_base_url() -> str:
    override = _env("LLM_BASE_URL", "")
    if override:
        return override.rstrip("/")
    return _LLM_BASES.get(LLM_BACKEND, _LLM_BASES["openrouter"]).rstrip("/")


def llm_api_key() -> str:
    if LLM_BACKEND == "xai":
        return XAI_API_KEY
    if LLM_BACKEND == "ollama":
        return _env("OLLAMA_API_KEY", "ollama")
    return OPENROUTER_API_KEY


def telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN) and bool(TELEGRAM_CHAT_IDS)
