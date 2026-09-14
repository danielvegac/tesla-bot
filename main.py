"""Tesla Familia Bot entrypoint — CLI, trip monitor, Telegram (iPhone)."""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import List, Optional

import config
from agent import FamiliaAgent
from command_handler import CommandHandler
import family_actions
from telegram_bot import TelegramBot
from tesla_client import TeslaAPIError, TeslaClient
from trip_logger import TripLogger
from trip_monitor import TripMonitor

HELLO_ASLEEP = "Hola. Estoy en reposo. Escríbeme si me necesitas."
HELLO_AWAKE = "Hola. Tesla despierto."
HELLO_FALLBACK = "Hola. Ya estoy aquí."


def _startup_ping_enabled() -> bool:
    raw = os.getenv("TELEGRAM_STARTUP_PING", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


async def _hello_line(tesla: TeslaClient) -> str:
    try:
        vehicles = await tesla.list_vehicles()
    except TeslaAPIError:
        return HELLO_FALLBACK
    vin = (getattr(tesla, "vin", "") or "").upper()
    match = None
    for item in vehicles or []:
        if str(item.get("vin", "")).upper() == vin:
            match = item
            break
    if match is None and vehicles:
        match = vehicles[0]
    state = str((match or {}).get("state") or "").lower()
    if state == "online":
        return HELLO_AWAKE
    if state in {"asleep", "offline"}:
        return HELLO_ASLEEP
    return HELLO_FALLBACK


@dataclass
class App:
    tesla: TeslaClient
    logger: TripLogger
    telegram: TelegramBot
    handler: CommandHandler
    monitor: TripMonitor

    async def aclose(self) -> None:
        await self.monitor.stop()
        await self.tesla.aclose()
        await self.telegram.aclose()
        self.logger.close()


def build_app(
    *,
    demo: Optional[bool] = None,
    poll_seconds: Optional[float] = None,
    park_debounce_polls: int = 2,
) -> App:
    tesla = TeslaClient(demo=demo)
    logger = TripLogger()
    telegram = TelegramBot()
    handler = CommandHandler(tesla=tesla, logger=logger, telegram=telegram)
    monitor = TripMonitor(
        tesla=tesla,
        logger=logger,
        poll_seconds=poll_seconds,
        park_debounce_polls=park_debounce_polls,
        on_trip_end=handler.on_trip_end,
        on_snapshot=handler.on_snapshot,
    )
    handler.attach_monitor(monitor)
    return App(
        tesla=tesla,
        logger=logger,
        telegram=telegram,
        handler=handler,
        monitor=monitor,
    )


def _banner(app: App) -> None:
    mode = "DEMO" if app.tesla.demo else "LIVE"
    if app.telegram.demo:
        tg = "console demo"
    elif app.telegram.commands_allowed:
        tg = "Telegram API"
    else:
        tg = "Telegram SETUP (falta CHAT_IDS)"
    print("Tesla Familia Bot")
    print(f"   Tesla: {mode}  |  Notificaciones: {tg}")
    print(f"   Región API: {config.TESLA_REGION} → {config.get_tesla_base_url()}")
    print("   Salir: exit / salir / Ctrl+C\n")


async def run_cli(app: App) -> None:
    _banner(app)
    await app.monitor.start()
    try:
        while True:
            try:
                cmd = await asyncio.to_thread(input, "Command: ")
            except EOFError:
                break
            if cmd.lower().strip() in {"exit", "quit", "salir"}:
                break
            await app.handler.handle(cmd)
    finally:
        await app.monitor.stop()


async def run_monitor_only(app: App) -> None:
    await app.monitor.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await app.monitor.stop()


async def run_cli_no_monitor(app: App) -> None:
    while True:
        try:
            cmd = await asyncio.to_thread(input, "Command: ")
        except EOFError:
            break
        if cmd.lower().strip() in {"exit", "quit", "salir"}:
            break
        await app.handler.handle(cmd)


async def run_telegram(app: App, *, setup: bool = False) -> None:
    _banner(app)
    if not app.telegram.token:
        print("Falta TELEGRAM_BOT_TOKEN en .env")
        return
    try:
        me = await app.telegram.get_me()
    except Exception as exc:
        print(f"No pude hablar con api.telegram.org: {exc}")
        return
    if not me.get("ok"):
        print(f"Token rechazado: {me}")
        return
    print(f"   Bot: @{(me.get('result') or {}).get('username') or '?'}")

    if not setup:
        await app.monitor.start()
        if app.telegram.commands_allowed and _startup_ping_enabled():
            line = await _hello_line(app.tesla)
            print(f"[Telegram] hello: {line}")
            await app.handler.notify_family(line)

    agent = FamiliaAgent(tesla=app.tesla)

    async def on_text(cmd: str, chat_id: str) -> str:
        print(f"[Telegram cmd] {cmd}")
        direct = await family_actions.handle_direct(app.tesla, cmd, logger=app.logger)
        if direct is not None:
            await app.telegram.send_message(direct, chat_id=chat_id)
            return direct
        if agent.enabled:
            print("[Agent] NL fallback")
            text = await agent.reply(cmd, chat_id=str(chat_id))
            await app.telegram.send_message(text, chat_id=chat_id)
            return text
        text = await app.handler.handle(cmd)
        await app.telegram.send_message(text, chat_id=chat_id)
        return text

    try:
        await app.telegram.poll_commands(app.handler, setup=setup, on_text=on_text)
    finally:
        await app.monitor.stop()


async def async_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tesla Familia Bot")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--no-monitor", action="store_true")
    parser.add_argument("--telegram", action="store_true")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)
    app = build_app(demo=True if args.demo else None)
    try:
        if args.telegram:
            await run_telegram(app, setup=args.setup)
        elif args.monitor:
            await run_monitor_only(app)
        elif args.no_monitor:
            await run_cli_no_monitor(app)
        else:
            await run_cli(app)
    finally:
        await app.aclose()
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
