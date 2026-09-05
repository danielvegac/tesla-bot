# Changelog

All notable changes and milestones for Tesla Familia Bot.

## [Unreleased]

### Added
- Live Fleet API access with full scopes (`vehicle_device_data`, `vehicle_cmds`, `vehicle_charging_cmds`, `vehicle_location`, etc.)
- Successful partner domain registration for `danielvegac.github.io` (app **523a361f**)
- Live vehicle data retrieval working (VIN LRWYGCFJ0TC568877)
- Family-style status message format confirmed in terminal
- Virtual Key paired on the owner account; `tesla-http-proxy` on `127.0.0.1:4443`
- Signed `flash_lights` while parked (curl + `python3 -m tesla_client`)
- Telegram **inbound** long-poll: `python3 main.py --telegram` and `--telegram --setup`
- Amateur BotFather guide: `docs/TELEGRAM_SETUP.md`
- Family allowlist via `TELEGRAM_CHAT_IDS` (unknown chats cannot lock/flash/nav)

### Known limitations
- Telegram only answers while the Mac process is running (no webhook, no 24/7 yet)
- Token refresh not yet implemented (issue #4; refresh tokens are single-use)
- Do not use developer app `8176c514` — domain already bound to `523a361f`
- WhatsApp unofficial APIs still deferred (ban risk)

## [0.1.0] - 2026-07-17

### Added
- Initial modular architecture (`TeslaClient`, `TripLogger`, `TripMonitor`, `CommandHandler`, `TelegramBot`)
- Demo mode for local testing without credentials
- Spanish/English command parsing
- Trip detection and cost calculation (home electricity + Supercharger rates)
- Charge reminder logic
