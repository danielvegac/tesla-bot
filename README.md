# Tesla Familia Bot

Bot familiar para consultar y controlar un Tesla Model Y, registrar viajes con odómetro real y avisar por **Telegram** (batería baja, carga lista, viaje terminado).

Funciona en **modo demo** sin credenciales y en **modo live** con Tesla Fleet API + bot oficial de Telegram.

Canal de mensajería: **Telegram primero** (API oficial). WhatsApp no oficial se pospone — riesgo de ban y mantenimiento feo para un bot familiar.

## Features

- **Tesla Fleet API** — estado, carga, clima, navegación, lock/unlock, claxon, luces
- **TripLogger** — distancia por odómetro, kWh, COP, eficiencia Wh/km
- **TripMonitor** — detecta inicio/fin de viaje por marcha y velocidad
- **Telegram** — notificaciones y comandos desde el iPhone (`estado`, `luces`, `carga`)
- **Comandos ES/EN** — `estado`, `carga 80`, `ir a Unicentro`, `viajes`, etc.
- **Demo mode** automático si no hay token

## Quick start (demo)

```bash
cd tesla-familia-bot
python3 -m pip install -r requirements.txt
python3 main.py --demo
```

Prueba en el CLI:

```
hola
estado
carga 80
clima
ir a Unicentro
bloquear
luces
viajes
ayuda
exit
```

Smoke tests:

```bash
python3 -m tesla_client
python3 -m trip_monitor
python3 -m telegram_bot
```

## Setup for real use

App Tesla a usar: `523a361f-12e3-4f22-a95e-b71348948b51` (owner `mccepedap`).  
**No uses** `8176c514` — el dominio `danielvegac.github.io` ya está tomado por la 523.

### 1. Environment

```bash
cp .env.example .env
```

Edita `.env` en `/Users/danielvega/Desktop/tesla-familia-bot` (nunca lo subas a git):

| Variable | Descripción |
|----------|-------------|
| `TESLA_ACCESS_TOKEN` | Bearer token Fleet API |
| `TESLA_REFRESH_TOKEN` | Refresh (single-use — rotar al usar) |
| `TESLA_VIN` | `LRWYGCFJ0TC568877` |
| `TESLA_REGION` | `na` (esta cuenta está en NA Fleet) |
| `TESLA_COMMAND_BASE_URL` | `https://127.0.0.1:4443` (proxy firmado) |
| `TESLA_COMMAND_HTTP_VERIFY` | `false` para el cert local del proxy |
| `TELEGRAM_BOT_TOKEN` | Token de [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_IDS` | IDs de chat de la familia, separados por coma |
| `HOME_ELECTRICITY_RATE` | COP por kWh en casa |
| `SUPERCHARGER_RATE` | COP por kWh Supercharger |
| `BATTERY_CAPACITY_KWH` | Capacidad usable (ej. 75) |
| `CHARGE_LOW_PERCENT` | Aviso de batería baja (default 20) |
| `TRIP_POLL_SECONDS` | Intervalo del monitor (default 45) |
| `DEMO_MODE` | `true` fuerza demo aunque haya token |

Zscaler en el Mac:

```bash
export SSL_CERT_FILE=$HOME/zscaler-chain.pem
```

### 2. Telegram (iPhone)

Guía paso a paso para amateur: **[docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md)**

Resumen:

1. iPhone → busca `@BotFather` (tilde azul) → `/newbot`
2. Nombre: `Tesla Familia`. Username: algo que termine en `bot`
3. Copia el token a `.env` → `TELEGRAM_BOT_TOKEN=...`
4. `python3 main.py --telegram --setup`
5. Escríbele `hola` al bot; te devuelve tu chat id
6. `TELEGRAM_CHAT_IDS=ese_numero` en `.env`
7. `python3 main.py --telegram` (o `caffeinate -i python3 main.py --telegram`)

Sin `TELEGRAM_CHAT_IDS` el bot **no** ejecuta `luces` / `desbloquear` / `carga 80`. Eso es a propósito.

El iPhone solo es el chat. El proceso vive en el Mac. Si el Mac se duerme, el bot no contesta.

### 3. Tesla Fleet API + proxy

Lecturas: token + VIN + región.

Escrituras (`luces`, lock, clima, límite de carga, nav): Docker `tesla-http-proxy` en `127.0.0.1:4443` con `keys-owner/private-key.pem`. Virtual Key ya está paired.

```bash
python3 -m tesla_client
```

debe devolver un snapshot `demo: false`. `flash_lights` solo en P.

### 4. Run

```bash
# CLI + monitor de viajes en segundo plano
python3 main.py

# Solo monitor (notifica viajes y carga)
python3 main.py --monitor

# CLI sin monitor
python3 main.py --no-monitor

# iPhone: escucha Telegram + monitor
python3 main.py --telegram

# iPhone: solo descubrir chat id (no mueve el carro)
python3 main.py --telegram --setup
```

## Commands (ES / EN)

| Comando | Acción |
|---------|--------|
| `hola` / `ping` | Estado del bot |
| `estado` / `status` | Snapshot completo |
| `batería` / `battery` | Solo SOC y carga |
| `rango` / `range` | Autonomía |
| `ubicación` / `location` | GPS + link Maps |
| `carga 80` / `charge 80` | Límite de carga |
| `estado carga` / `charging` | Detalle del cargador |
| `clima` / `precondition` | Encender clima |
| `apagar clima` / `climate off` | Apagar clima |
| `bloquear` / `lock` | Cerrar puertas |
| `desbloquear` / `unlock` | Abrir puertas |
| `claxon` / `honk` | Bocina |
| `luces` / `flash` | Destellar luces |
| `ir a X` / `go to X` | Navegación |
| `viajes` / `trips` | Últimos viajes |
| `viaje activo` / `active trip` | Viaje en curso |
| `resumen` / `summary` | Totales de hoy |
| `semana` / `week` | Totales 7 días |
| `monitor` | Estado del TripMonitor |
| `notificar` / `notify` | Reenviar estado por Telegram |
| `ayuda` / `help` | Lista de comandos |

## Architecture

```
main.py
  ├── TeslaClient      → Fleet API (reads) + proxy (signed writes)
  ├── TripLogger       → SQLite logs/trips.db
  ├── TripMonitor      → poll → start/end trips
  ├── TelegramBot      → sendMessage + getUpdates long-poll
  └── CommandHandler   → comandos ES/EN + avisos
```

Al terminar un viaje, el monitor llama `on_trip_end` → mensaje Telegram con km, kWh y COP. En cada poll, `on_snapshot` revisa batería baja / carga completa.

## Project layout

```
config.py               # env + rates
tesla_client.py         # Fleet API client
trip_logger.py          # SQLite trips
trip_monitor.py         # drive detection loop
telegram_bot.py         # Bot API send + long-poll
command_handler.py      # ES/EN commands + reminders
main.py                 # CLI / monitor / --telegram
whatsapp_bot.py         # stub (Telegram is primary)
docs/TELEGRAM_SETUP.md  # BotFather amateur guide
docs/STATUS.md
requirements.txt
.env.example
```

## Honesty / risks

- **Batería / wake:** cada `estado` puede despertar el carro. El monitor poll cada 45 s también. No lo dejes agresivo 24/7 sin mirar.
- **Telegram token = control del bot.** Allowlist de chat ids. No publiques `t.me/tu_bot` en un grupo abierto.
- **Mac dormido = bot muerto.** Esto todavía no es un servicio. Token Tesla ~8 h hasta el issue #4.
- **WhatsApp no oficial:** no. Ban + sesión que se cae. Familia primero, experiments después.
- **Comandos de escritura** solo con proxy + Virtual Key + auto en P para `luces`.

## Cost model

```
energy_kwh = (battery_used_pct / 100) * BATTERY_CAPACITY_KWH
cost_cop   = energy_kwh * HOME_ELECTRICITY_RATE   # or SUPERCHARGER_RATE
```

Ajusta las tarifas en `.env` a tus valores reales en Colombia.

## License

Uso personal / familiar. No afiliado a Tesla, Inc.
