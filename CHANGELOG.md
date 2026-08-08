# Changelog

All notable changes and milestones for Tesla Familia Bot.

## [Unreleased]

### Added
- Live Fleet API access with full scopes (`vehicle_device_data`, `vehicle_cmds`, `vehicle_charging_cmds`, `vehicle_location`, etc.)
- Successful partner domain registration for `danielvegac.github.io`
- Public key hosting and partner account registration completed
- Live vehicle data retrieval working (VIN LRWYGCFJ0TC568877)
- Family-style status message format confirmed in terminal

### Known limitations
- Vehicle Command Protocol (Virtual Key) still required for all write commands
- Token refresh not yet implemented
- Telegram/WhatsApp live delivery not yet wired with the new token

## [0.1.0] - 2026-07-17

### Added
- Initial modular architecture (`TeslaClient`, `TripLogger`, `TripMonitor`, `CommandHandler`, `TelegramBot`)
- Demo mode for local testing without credentials
- Spanish/English command parsing
- Trip detection and cost calculation (home electricity + Supercharger rates)
- Charge reminder logic
