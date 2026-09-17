# Tesla Familia Bot — Current Status

**Last updated:** 2026-09-17

## Working right now

| Capability | Status |
|------------|--------|
| Domain + public key on `danielvegac.github.io` | Bound to app **523a361f** |
| Fleet reads + proxy writes (flash/lock) | Live on the Mac |
| OAuth refresh on 401 | `tesla_oauth.py` + local client hook |
| Telegram `@teslafamilia_bot` allowlist `7502786075` | Live |
| Explicit nav with Nominatim pin | Unicentro / Casa |
| Unknown place | no pin, nothing sent |
| Home geofence 80 m | driveway `4.700454, -74.027738` |
| LFP weekly hook | seed + Telegram via `command_handler.on_snapshot` |
| Charge reminder | 35%, online and not charging |
| Direct flash / honk / lock / climate | Python path, before LLM |
| Daily trip digest on trip-end | count + km + % used + last SOC |

## Do not do

- Do **not** use Tesla developer app `8176c514` for this car/domain.
- Do **not** commit `.env`, tokens, or `private-key.pem`.
- Do **not** invent office coordinates. Work pin waits for live GPS + `WORK_LAT`/`WORK_LON`.
- Do **not** wire unofficial WhatsApp.

## Still open

| Capability | Status |
|------------|--------|
| Verify `logs/lfp_full.json` after an online Mac poll | waiting on Desktop process |
| Work alias at the office | code ready; pin not captured |
| Second Telegram chat id | allowlist already supports `id1,id2` |
| 24/7 host | Mac sleep still kills long-poll |
| Weekly LFP Telegram after a real 100% | code sends; needs a full charge event to prove the cycle |

## Key references

- VIN: `LRWYGCFJ0TC568877` (Model Y Juniper RWD LFP, Colombia, NA Fleet)
- Client ID: `523a361f-12e3-4f22-a95e-b71348948b51`
- Local folder: `/Users/danielvega/Desktop/tesla-familia-bot`
- Start: `cd ~/Desktop/tesla-familia-bot && ./start-bot.sh`
- Proxy: `TESLA_COMMAND_BASE_URL=https://127.0.0.1:4443`
- Zscaler: `SSL_CERT_FILE=$HOME/zscaler-chain.pem`
