# Changelog

All notable changes and milestones for Tesla Familia Bot.

## [Unreleased]

### 2026-09-14 — Direct car actions (no LLM lies)
- Python owns flash / honk / lock / climate / set_temps before Qwen.
- Wake copy is neutral agent voice (`Tesla despierto`), never feminine `despierta`.
- Lock always POSTs `door_lock` (no stale `locked=true` short-circuit).
- Climate copy only claims success after Tesla result; re-read `is_climate_on` when possible.
- Trip-end Telegram now appends today's digest (count, km, % used, last SOC).
- `set_temps` lives on TeslaClient when the Mac file has that method.

### 2026-09-14 — LFP hook + work pin scaffold
- `command_handler.on_snapshot` now calls `lfp_reminder.on_snapshot`. First online poll seeds `logs/lfp_full.json`; weekly copy only after 7 days below 99%.
- Work alias (`oficina` / `trabajo` / `jeeves`) resolves only if `WORK_LAT` + `WORK_LON` are set. No invented office coordinates.
- `geo.where_line` can say parked at work once that pin exists. Agent `get_vehicle` includes `where`.
- Defaults: `BATTERY_CAPACITY_KWH=60`, `CHARGE_LOW_PERCENT=35`, `CHARGE_REMINDER_TARGET=100`.

### Added
- Live Fleet API access with full scopes (`vehicle_device_data`, `vehicle_cmds`, `vehicle_charging_cmds`, `vehicle_location`, etc.)
- Successful partner domain registration for `danielvegac.github.io` (app **523a361f**)
- Live vehicle data retrieval working (VIN LRWYGCFJ0TC568877)
- Family-style status message format confirmed in terminal
- Virtual Key paired on the owner account; `tesla-http-proxy` on `127.0.0.1:4443`
- Signed `flash_lights` while parked (curl + `python3 -m tesla_client`)
- Telegram inbound long-poll: `python3 main.py --telegram` and `--telegram --setup`
- Amateur BotFather guide: `docs/TELEGRAM_SETUP.md`
- Family allowlist via `TELEGRAM_CHAT_IDS` (unknown chats cannot lock/flash/nav)

### Known limitations
- Telegram only answers while the Mac process is running (no webhook, no 24/7 yet)
- Token refresh is implemented on the Mac (`tesla_oauth.py`); keep one process only
- Do not use developer app `8176c514` — domain already bound to `523a361f`
- WhatsApp unofficial APIs still deferred (ban risk)

## [0.1.0] - 2026-07-17

### Added
- Initial modular architecture (`TeslaClient`, `TripLogger`, `TripMonitor`, `CommandHandler`, `TelegramBot`)
- Demo mode for local testing without credentials
- Spanish/English command parsing
- Trip detection and cost calculation (home electricity + Supercharger rates)
- Charge reminder logic
