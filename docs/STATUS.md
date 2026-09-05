# Tesla Familia Bot — Current Status

**Last updated:** 2026-09-05

## Working right now

| Capability | Status |
|------------|--------|
| Domain + public key on `danielvegac.github.io` | ✅ Bound to app **523a361f** |
| Partner / owner token (account `mccepedap`) | ✅ Live |
| List vehicles + wake + `vehicle_data` | ✅ Live (VIN `LRWYGCFJ0TC568877`) |
| Family-style `estado` | ✅ CLI confirmed |
| Virtual Key paired (`fleet_status` key_paired_vins) | ✅ Done 2026-09-05 |
| `tesla-http-proxy` on `127.0.0.1:4443` (`keys-owner`) | ✅ Writes |
| `flash_lights` while parked | ✅ curl + `python3 -m tesla_client` |
| Telegram sendMessage helper | ✅ Code |
| Telegram inbound long-poll (`--telegram`) | ✅ Code 2026-09-05 — needs BotFather token on the Mac |
| Trip logging architecture | ✅ Code exists |

## Do not do

- Do **not** use Tesla developer app `8176c514-862e-4fc2-948c-0e4e7d9f7310` for this car/domain. `danielvegac.github.io` is already taken by app `523a361f-12e3-4f22-a95e-b71348948b51`.
- Do **not** commit `.env`, tokens, or `private-key.pem`.
- Do **not** wire unofficial WhatsApp. Official Telegram first.

## Still open

| Capability | Status | Reason |
|------------|--------|--------|
| Telegram live from iPhone | 🟡 waiting on you | Create bot in BotFather, put token + chat id in `.env`, run `python3 main.py --telegram` (see `docs/TELEGRAM_SETUP.md`) |
| Lock / climate / charge limit / nav from phone | 🟡 code ready | Needs proxy up + Telegram allowlist. Re-test each command after `luces` |
| Automatic token refresh | ❌ | Issue #4 — refresh tokens are single-use |
| 24/7 without the Mac awake | ❌ | Long-poll dies if the laptop sleeps |
| WhatsApp | ❌ deferred | Ban risk on unofficial APIs |

## Current priority

1. BotFather + `--telegram --setup` + allowlist chat ids  
2. From iPhone: `estado` (read) then `luces` (write, car in P)  
3. Issue #4 token refresh so the bot survives more than ~8 hours  
4. Charge reminders + trip-end push while `--telegram` is running  

## Key references

- VIN: `LRWYGCFJ0TC568877` (Model Y, Colombia, NA Fleet)
- Domain: `danielvegac.github.io`
- Client ID to use: `523a361f-12e3-4f22-a95e-b71348948b51`
- Virtual Key link: https://tesla.com/_ak/danielvegac.github.io
- Local folder: `/Users/danielvega/Desktop/tesla-familia-bot`
- Proxy: `TESLA_COMMAND_BASE_URL=https://127.0.0.1:4443` + `TESLA_COMMAND_HTTP_VERIFY=false`
- Zscaler (Tesla HTTPS): `SSL_CERT_FILE=$HOME/zscaler-chain.pem`

## Open Issues

- #2 – Virtual Key pairing — **done on the car**; leave open until remaining writes are re-tested from Telegram
- #3 – Status notifications + trip logging — Telegram inbound added; delivery still unconfirmed until BotFather token exists
- #4 – Automatic token refresh
- #5 – Vehicle control commands — unblocked on Mac (`flash_lights`); next is the same commands from Telegram
