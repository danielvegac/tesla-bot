"""Per-chat session state for the family agent."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentState:
    vehicle: str = "unknown"
    pending_write: Optional[str] = None
    pending_nav: Optional[str] = None
    resume_after_wake: Optional[str] = None
    last_nav: Optional[str] = None
    last_nav_at: float = 0.0
    last_vehicle: Optional[Dict[str, Any]] = field(default=None)

    def mark_nav_sent(self, dest: str) -> None:
        self.last_nav = dest
        self.last_nav_at = time.time()
        self.pending_nav = None

    def screen_answer(self, *, spanish: bool = True) -> str:
        if not self.last_nav:
            if spanish:
                return "No he mandado ningún destino en esta sesión. Dime a dónde ir."
            return "I have not sent a destination this session."
        age = int(time.time() - self.last_nav_at)
        if spanish:
            return (
                f"Mandé *{self.last_nav}* al mapa y Tesla aceptó el comando. "
                f"No veo la pantalla; mírala en el carro. ({age}s)"
            )
        return (
            f"I sent *{self.last_nav}* and Tesla accepted it. "
            f"I cannot see the screen; check the car. ({age}s)"
        )
