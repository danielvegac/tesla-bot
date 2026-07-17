# Tesla Familia Bot

Bot familiar para consultar y controlar un Tesla, registrar viajes con odómetro real y avisar por **Telegram** (batería baja, carga lista, viaje terminado).

Funciona en **modo demo** sin credenciales (ideal para probar) y en **modo live** con Tesla Fleet API + bot de Telegram.

## Features

- **Tesla Fleet API** — estado, carga, clima, navegación, lock/unlock, claxon, luces
- **TripLogger** — distancia por odómetro, kWh, COP, eficiencia Wh/km
- **TripMonitor** — detecta inicio/fin de viaje por marcha y velocidad
- **Telegram** — notificaciones a chats de la familia
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
viajes
ayuda
exit
```

Smoke tests:

```bash
python3 -m tesla_client
python3 -m trip_monitor
```

## Setup for real use

### 1. Environment

```bash
cp .env.example .env
```

Edita `.env`:

| Variable | Descripción |
|----------|-------------|
| `TESLA_ACCESS_TOKEN` | Bearer token Fleet API |
| `TESLA_VIN` | VIN del vehículo |
| `TESLA_REGION` | `na`, `eu` o `cn` |
| `TELEGRAM_BOT_TOKEN` | Token de [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_IDS` | IDs de chat (usuario o grupo), separados por coma |
| `HOME_ELECTRICITY_RATE` | COP por kWh en casa |
| `SUPERCHARGER_RATE` | COP por kWh Supercharger |
| `BATTERY_CAPACITY_KWH` | Capacidad usable (ej. 75) |
| `CHARGE_LOW_PERCENT` | Aviso de batería baja (default 20) |
| `TRIP_POLL_SECONDS` | Intervalo del monitor (default 45) |
| `DEMO_MODE` | `true` fuerza demo aunque haya token |

### 2. Telegram

1. Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el token.
2. Envía un mensaje a tu bot.
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia `chat.id`.
4. Pon token y chat id(s) en `.env`.

### 3. Tesla Fleet API

1. Obtén un access token con scopes de datos y comandos del vehículo.
2. Configura `TESLA_ACCESS_TOKEN`, `TESLA_VIN` y la región correcta.
3. `python3 -m tesla_client` debería devolver un snapshot `demo: false`.

> **Nota:** en vehículos recientes, algunos *comandos* requieren Vehicle Command Protocol (clave virtual / proxy firmado). La lectura de `vehicle_data` funciona con el bearer token. Si un comando falla por firma, el bot reportará el error de la API.

### 4. Run

```bash
# CLI + monitor de viajes en segundo plano
python3 main.py

# Solo monitor (notifica viajes y carga)
python3 main.py --monitor

# CLI sin monitor
python3 main.py --no-monitor
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
  ├── TeslaClient      → Fleet API (o demo)
  ├── TripLogger       → SQLite logs/trips.db
  ├── TripMonitor      → poll → start/end trips
  ├── TelegramBot      → notificaciones familia
  └── CommandHandler   → comandos ES/EN + avisos
```

Al terminar un viaje, el monitor llama `on_trip_end` → mensaje Telegram con km, kWh y COP. En cada poll, `on_snapshot` revisa batería baja / carga completa.

## Project layout

```
config.py           # env + rates
tesla_client.py     # Fleet API client
trip_logger.py      # SQLite trips
trip_monitor.py     # drive detection loop
telegram_bot.py     # Bot API sendMessage
command_handler.py  # ES/EN commands + reminders
main.py             # CLI / monitor entry
whatsapp_bot.py     # stub (Telegram is primary)
requirements.txt
.env.example
```

## Cost model

```
energy_kwh = (battery_used_pct / 100) * BATTERY_CAPACITY_KWH
cost_cop   = energy_kwh * HOME_ELECTRICITY_RATE   # or SUPERCHARGER_RATE
```

Ajusta las tarifas en `.env` a tus valores reales en Colombia (u otro país).

## License

Uso personal / familiar. No afiliado a Tesla, Inc.
