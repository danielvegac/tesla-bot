"""Telegram Bot API for Tesla Familia Bot.

Official Bot API only (no unofficial clients).

Two jobs:
  1. sendMessage — family notifications (trip end, battery, charge ready)
  2. getUpdates long-poll — receive commands from iPhone Telegram

No webhook. A home Mac behind Zscaler cannot easily expose HTTPS.
The bot only answers while this process is running on the Mac.

If TELEGRAM_CHAT_IDS is empty, the bot is in setup mode: it tells you
your chat id and will NOT run vehicle commands (lock/flash/nav).
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

import config

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


FAMILY_COMMANDS = [
    {"command": "start", "description": "Saludo / estado del bot"},
    {"command": "ayuda", "description": "Lista de comandos"},
    {"command": "estado", "description": "Batería, rango, puertas, clima"},
    {"command": "bateria", "description": "Solo nivel de batería"},
    {"command": "carga", "description": "Estado del cargador (o: carga 80)"},
    {"command": "luces", "description": "Destellar luces (auto en P)"},
    {"command": "clima", "description": "Preacondicionar cabina"},
    {"command": "bloquear", "description": "Cerrar puertas"},
    {"command": "desbloquear", "description": "Abrir puertas"},
    {"command": "viajes", "description": "Últimos viajes"},
]

MAX_COMMANDS_PER_BUBBLE = 8


def normalize_incoming_text(text: str) -> str:
    """Turn Telegram '/estado@MyBot' into 'estado' for CommandHandler."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("/"):
        raw = raw[1:]
        first, *rest = raw.split(None, 1)
        first = first.split("@", 1)[0]
        raw = " ".join([first] + rest).strip()
    lowered = raw.lower()
    if lowered in {"start", "startbot"}:
        return "hola"
    return raw


def split_commands(text: str) -> List[str]:
    """One Telegram bubble may contain several commands (newlines or ;).

    Does not split on spaces, so 'ir a Unicentro' stays one command.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    parts: List[str] = []
    for chunk in re.split(r"[\r\n;]+", raw):
        chunk = chunk.strip().strip("-•*").strip()
        if chunk:
            parts.append(chunk)
    return parts[:MAX_COMMANDS_PER_BUBBLE]


class TelegramBot:
    """Send notifications and (optionally) receive family commands."""

    API_BASE = "https://api.telegram.org"

    def __init__(
        self,
        token: Optional[str] = None,
        chat_ids: Optional[Sequence[str]] = None,
        demo: Optional[bool] = None,
    ):
        self.token = token if token is not None else config.TELEGRAM_BOT_TOKEN
        self.chat_ids: List[str] = [
            str(x) for x in (chat_ids if chat_ids is not None else config.TELEGRAM_CHAT_IDS)
        ]
        if demo is None:
            self.demo = not bool(self.token)
        else:
            self.demo = demo
        self._client: Optional[Any] = None
        self.sent_messages: List[Dict[str, Any]] = []
        self._offset: int = 0
        self.bot_username: str = ""

    @property
    def enabled(self) -> bool:
        return True

    @property
    def can_receive(self) -> bool:
        return bool(self.token) and not self.demo

    @property
    def commands_allowed(self) -> bool:
        """Vehicle commands only after at least one family chat id is set."""
        return bool(self.chat_ids)

    def is_allowed_chat(self, chat_id: str) -> bool:
        if not self.chat_ids:
            return False
        return str(chat_id) in set(self.chat_ids)

    def _api_url(self, method: str) -> str:
        return f"{self.API_BASE}/bot{self.token}/{method}"

    async def _get_http(self) -> Any:
        if httpx is None:
            raise RuntimeError("httpx is not installed. Run: pip install -r requirements.txt")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=45.0)
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
        parse_mode: Optional[str] = "Markdown",
    ) -> bool:
        """Send to one chat or broadcast to all configured chats."""
        targets = [str(chat_id)] if chat_id else list(self.chat_ids)
        if not targets:
            targets = ["demo"]

        ok_all = True
        for target in targets:
            record = {"chat_id": str(target), "text": text, "demo": self.demo}
            self.sent_messages.append(record)

            if self.demo:
                print(f"[Telegram/demo → {target}] {text}")
                continue

            ok_all = await self._post_message(target, text, parse_mode) and ok_all

        return ok_all

    async def _post_message(
        self,
        target: str,
        text: str,
        parse_mode: Optional[str],
    ) -> bool:
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
                if parse_mode:
                    return await self._post_message(target, text, None)
                print(
                    f"[Telegram] error {response.status_code} to {target}: "
                    f"{response.text[:300]}"
                )
                return False
            print(f"[Telegram → {target}] sent ({len(text)} chars)")
            return True
        except Exception as exc:
            print(f"[Telegram] network error to {target}: {exc}")
            return False

    async def broadcast(self, text: str) -> bool:
        return await self.send_message(text)

    async def get_me(self) -> Dict[str, Any]:
        if self.demo or not self.token:
            return {"ok": False, "demo": True}
        client = await self._get_http()
        response = await client.get(self._api_url("getMe"))
        data = response.json()
        if data.get("ok"):
            self.bot_username = data.get("result", {}).get("username") or ""
        return data

    async def delete_webhook(self) -> None:
        """Polling and webhook cannot run at the same time."""
        if self.demo or not self.token:
            return
        try:
            client = await self._get_http()
            await client.post(self._api_url("deleteWebhook"), json={"drop_pending_updates": False})
        except Exception as exc:
            print(f"[Telegram] deleteWebhook failed (ok to ignore): {exc}")

    async def register_commands(self) -> None:
        """Puts the command menu on iPhone (the '/' button)."""
        if self.demo or not self.token:
            return
        try:
            client = await self._get_http()
            response = await client.post(
                self._api_url("setMyCommands"),
                json={"commands": FAMILY_COMMANDS},
            )
            if response.status_code >= 400:
                print(f"[Telegram] setMyCommands failed: {response.text[:200]}")
            else:
                print("[Telegram] menú de comandos publicado en el bot")
        except Exception as exc:
            print(f"[Telegram] setMyCommands error: {exc}")

    async def get_updates(self, offset: int = 0, timeout: int = 30) -> List[Dict[str, Any]]:
        if self.demo or not self.token:
            return []
        client = await self._get_http()
        response = await client.get(
            self._api_url("getUpdates"),
            params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": '["message"]',
            },
            timeout=timeout + 10,
        )
        data = response.json()
        if not data.get("ok"):
            print(f"[Telegram] getUpdates error: {data}")
            return []
        return list(data.get("result") or [])

    async def drop_pending_updates(self) -> None:
        """Skip old messages so we don't replay luces/unlock from last night."""
        if self.demo or not self.token:
            return
        try:
            client = await self._get_http()
            response = await client.get(
                self._api_url("getUpdates"),
                params={"offset": -1, "timeout": 0},
            )
            data = response.json()
            results = data.get("result") or []
            if results:
                last_id = results[-1]["update_id"]
                await client.get(
                    self._api_url("getUpdates"),
                    params={"offset": last_id + 1, "timeout": 0},
                )
                self._offset = last_id + 1
                print(f"[Telegram] descartados updates viejos (offset={self._offset})")
        except Exception as exc:
            print(f"[Telegram] drop_pending failed: {exc}")

    async def poll_commands(
        self,
        handler: Any,
        *,
        setup: bool = False,
        on_text: Optional[Callable[[str, str], Awaitable[str]]] = None,
    ) -> None:
        """Block and handle incoming messages until cancelled.

        setup=True or empty TELEGRAM_CHAT_IDS → only print/reply the chat id.
        Never run vehicle writes until the family chat is allowlisted.
        """
        if not self.can_receive:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN vacío. Sigue docs/TELEGRAM_SETUP.md"
            )

        await self.delete_webhook()
        await self.drop_pending_updates()
        await self.register_commands()

        print("[Telegram] esperando mensajes del iPhone… Ctrl+C para salir.")
        if setup or not self.commands_allowed:
            print(
                "[Telegram] MODO SETUP — no se ejecutan comandos del carro "
                "hasta que pongas TELEGRAM_CHAT_IDS en .env"
            )

        while True:
            try:
                updates = await self.get_updates(offset=self._offset, timeout=30)
            except Exception as exc:
                print(f"[Telegram] poll error: {exc} — reintento en 5s")
                await _sleep(5)
                continue

            for update in updates:
                self._offset = int(update["update_id"]) + 1
                await self._handle_update(update, handler, setup=setup, on_text=on_text)

    async def _handle_update(
        self,
        update: Dict[str, Any],
        handler: Any,
        *,
        setup: bool,
        on_text: Optional[Callable[[str, str], Awaitable[str]]] = None,
    ) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        if not chat_id:
            return

        from_user = message.get("from") or {}
        who = from_user.get("username") or from_user.get("first_name") or "?"
        text = message.get("text")
        if not text:
            await self.send_message(
                "✍️ Escribe un comando de texto. Prueba: estado",
                chat_id=chat_id,
                parse_mode=None,
            )
            return

        print(f"[Telegram ← {who} / {chat_id}] {text}")

        if setup or not self.commands_allowed or not self.is_allowed_chat(chat_id):
            await self.send_message(
                _setup_reply(chat_id, who, allowed=self.is_allowed_chat(chat_id)),
                chat_id=chat_id,
                parse_mode=None,
            )
            return

        commands = [normalize_incoming_text(part) for part in split_commands(text)]
        commands = [c for c in commands if c]
        if not commands:
            return

        if on_text is not None:
            for cmd in commands:
                await on_text(cmd, chat_id)
            return

        replies: List[str] = []
        for cmd in commands:
            print(f"[Telegram cmd] {cmd}")
            replies.append(await handler.handle(cmd))
        await self.send_message("\n\n".join(replies), chat_id=chat_id)

    def clear_history(self) -> None:
        self.sent_messages.clear()

    def last_message_text(self) -> Optional[str]:
        if not self.sent_messages:
            return None
        return self.sent_messages[-1]["text"]


def _setup_reply(chat_id: str, who: str, *, allowed: bool) -> str:
    if allowed:
        return (
            f"Hola {who}. Este chat YA está autorizado, pero el bot arrancó "
            f"en modo setup.\nReinicia sin --setup:\n\n"
            f"python3 main.py --telegram"
        )
    return (
        f"Hola {who}. Soy Tesla Familia Bot.\n\n"
        f"Tu chat id es:\n{chat_id}\n\n"
        f"1. Ábrelo en el Mac:\n"
        f"   nano ~/Desktop/tesla-familia-bot/.env\n"
        f"2. Pon esta línea (varios ids separados por coma):\n"
        f"   TELEGRAM_CHAT_IDS={chat_id}\n"
        f"3. Guarda, y en la terminal:\n"
        f"   python3 main.py --telegram\n\n"
        f"Hasta que hagas eso NO muevo el carro (por seguridad)."
    )


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        bot = TelegramBot(demo=True)
        await bot.send_message("Hola familia (demo)")
        print("normalize:", normalize_incoming_text("/estado@TeslaFamiliaBot"))
        print("split:", split_commands("hola\nestado\nluces"))
        await bot.aclose()

    asyncio.run(_demo())
