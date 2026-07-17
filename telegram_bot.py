"""Telegram Bot API notifier for Tesla Familia Bot.

Uses the official Bot API (sendMessage). When TELEGRAM_BOT_TOKEN or chat IDs
are missing, runs in console demo mode so local testing still works.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import config

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


class TelegramBot:
    """Send text notifications to one or more Telegram chats."""

    API_BASE = "https://api.telegram.org"

    def __init__(
        self,
        token: Optional[str] = None,
        chat_ids: Optional[Sequence[str] ] = None,
        demo: Optional[bool] = None,
    ):
        self.token = token if token is not None else config.TELEGRAM_BOT_TOKEN
        self.chat_ids: List[str] = list(
            chat_ids if chat_ids is not None else config.TELEGRAM_CHAT_IDS
        )
        if demo is None:
            self.demo = not (bool(self.token) and bool(self.chat_ids))
        else:
            self.demo = demo
        self._client: Optional[Any] = None
        # Captured messages for tests / inspection in demo mode
        self.sent_messages: List[Dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return True  # always can "send" (demo prints)

    def _api_url(self, method: str) -> str:
        return f"{self.API_BASE}/bot{self.token}/{method}"

    async def _get_http(self) -> Any:
        if httpx is None:
            raise RuntimeError("httpx is not installed. Run: pip install -r requirements.txt")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        *,
        parse_mode: Optional[str] = None,
    ) -> bool:
        """Send to one chat or broadcast to all configured chats."""
        targets = [chat_id] if chat_id else list(self.chat_ids)
        if not targets:
            targets = ["demo"]

        ok_all = True
        for target in targets:
            record = {"chat_id": str(target), "text": text, "demo": self.demo}
            self.sent_messages.append(record)

            if self.demo:
                print(f"[Telegram/demo → {target}] {text}")
                continue

            try:
                client = await self._get_http()
                payload: Dict[str, Any] = {
                    "chat_id": target,
                    "text": text,
                    "disable_web_page_preview": True,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                response = await client.post(self._api_url("sendMessage"), json=payload)
                if response.status_code >= 400:
                    ok_all = False
                    print(
                        f"[Telegram] error {response.status_code} to {target}: "
                        f"{response.text[:300]}"
                    )
                else:
                    print(f"[Telegram → {target}] sent ({len(text)} chars)")
            except Exception as exc:
                ok_all = False
                print(f"[Telegram] network error to {target}: {exc}")

        return ok_all

    async def broadcast(self, text: str) -> bool:
        return await self.send_message(text)

    def clear_history(self) -> None:
        self.sent_messages.clear()

    def last_message_text(self) -> Optional[str]:
        if not self.sent_messages:
            return None
        return self.sent_messages[-1]["text"]
