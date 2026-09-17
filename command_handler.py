"""Parse family chat commands (ES/EN) and dispatch Tesla actions + notifications."""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import config
import lfp_reminder
from telegram_bot import TelegramBot
from tesla_client import TeslaAPIError, TeslaClient
from trip_logger import TripLogger

if TYPE_CHECKING:
    from trip_monitor import TripMonitor
