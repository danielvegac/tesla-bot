# Telegram setup — Tesla Familia Bot

Guía para alguien que nunca ha creado un bot. Hazlo en el **iPhone** (o en Telegram Desktop). No necesitas saber programar para los pasos 1–6.

El bot de Telegram **no vive dentro del iPhone**. Telegram solo es el chat. El programa corre en tu **Mac**. Si el Mac se duerme o cierras la terminal, el bot deja de contestar.

No uses WhatsApp no oficial. Telegram Bot API es el canal estable para la familia.

---

## Lo que vas a obtener

- Un bot con nombre tipo **Tesla Familia**.
- Un **token** (contraseña del bot). Va solo en `.env`, nunca a GitHub.
- Tu **chat id** (número de tu conversación). También solo en `.env`.
- En el iPhone: escribes `estado`, `luces`, `carga 80` y el Mac habla con el Model Y.

---

## Paso 1 — Abre BotFather (el bot oficial)

1. Abre **Telegram** en el iPhone.
2. Arriba, toca la lupa (buscar).
3. Escribe: `BotFather`
4. Entra al resultado que tenga:
   - usuario **@BotFather**
   - **tilde azul** de cuenta verificada
5. Toca **Start** / **Iniciar**.

Si ves varios “BotFather”, el falso no tiene tilde azul. No le des token a nadie.

---

## Paso 2 — Crea el bot

En el chat con BotFather escribe exactamente:

```
/newbot
```

BotFather pregunta dos cosas.

### 2a. Nombre visible (display name)

Esto sale arriba del chat. Puede tener espacios y tildes.

Recomendado:

```
Tesla Familia
```

### 2b. Username (único en todo Telegram)

Reglas duras:

- solo letras inglesas, números y `_`
- **tiene que terminar en `bot`**
- si está ocupado, prueba otro

Prueba en este orden:

```
TeslaFamiliaDanielBot
```

```
TeslaFamiliaYBot
```

```
FamiliaModelYBot
```

Cuando funcione, BotFather responde con algo así:

```
Done! Congratulations on your new bot.
...
Use this token to access the HTTP API:
1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Esa línea con los **dos puntos** es el token.

---

## Paso 3 — Guarda el token (esto es una contraseña)

Trátalo como la llave del carro + el chat de la familia.

- **Sí:** pégalo en `.env` del Mac (abajo).
- **No:** no lo mandes por WhatsApp, no lo pongas en un issue de GitHub, no lo subas al repo, no lo pegues en un chat de Grok si puedes evitarlo.
- Si se filtra: en BotFather usa `/revoke` y te da un token nuevo. El viejo muere al instante.

Cópialo a Notas del iPhone un momento, o mejor pásalo al Mac por AirDrop / iMessage contigo mismo, y bórralo de Notas después.

---

## Paso 4 — Opcional, pero queda más claro para la familia

Sigue en BotFather:

```
/setdescription
```

Elige tu bot y pega:

```
Bot de la familia para el Model Y. Comandos: estado, luces, carga, clima.
```

```
/setabouttext
```

```
Tesla Familia — solo chats autorizados.
```

```
/setuserpic
```

Sube una foto (logo Tesla, foto del Y, lo que quieras).

```
/setjoingroups
```

Elige tu bot → **Disable**.  
Así extraños no lo meten a un grupo random.

No hace falta `/setprivacy` si solo lo usas en chat privado.

---

## Paso 5 — Ábrelo una vez desde el iPhone

BotFather te da un link `t.me/TuUserBot`. Ábrelo y toca **Start**.

Todavía **no** va a contestar comandos del carro. El Mac todavía no está escuchando.

---

## Paso 6 — Pon el token en el Mac

En Terminal:

```bash
cd ~/Desktop/tesla-familia-bot
nano .env
```

Busca estas dos líneas (o agrégalas si no están):

```
TELEGRAM_BOT_TOKEN=pega_aqui_el_token_sin_comillas
TELEGRAM_CHAT_IDS=
```

Guarda: `Ctrl+O`, Enter, `Ctrl+X`.

El archivo `.env` ya está en `.gitignore`. No lo subas.

---

## Paso 7 — Descubre tu chat id (modo setup)

El chat id **no** es tu número de celular. Es un número largo que Telegram asigna a *tu* conversación con *este* bot. Cada familiar tiene el suyo.

1. Confirma que el proxy Tesla sigue arriba si más tarde quieres `luces`:

   ```bash
   docker ps
   ```

2. Arranca el bot en modo setup (no mueve el carro):

   ```bash
   cd ~/Desktop/tesla-familia-bot
   export SSL_CERT_FILE=$HOME/zscaler-chain.pem
   python3 main.py --telegram --setup
   ```

3. En el iPhone, ábrele un chat al bot y escribe:

   ```
   hola
   ```

4. El bot debe responder con **tu chat id** (un número, a veces negativo si es un grupo).
5. En el Mac verás la misma línea en la terminal.

Si `python3 main.py --telegram --setup` se cae con error de red hacia `api.telegram.org`:

- Zscaler / red de trabajo a veces bloquea Telegram.
- Prueba red de casa, hotspot del celular, o desactiva VPN.
- `SSL_CERT_FILE=$HOME/zscaler-chain.pem` es para Tesla, no arregla un bloqueo de Telegram.

---

## Paso 8 — Autoriza solo a la familia

Otra vez:

```bash
nano ~/Desktop/tesla-familia-bot/.env
```

Ejemplo con un solo teléfono (el tuyo):

```
TELEGRAM_CHAT_IDS=123456789
```

Ejemplo con dos personas:

```
TELEGRAM_CHAT_IDS=123456789,987654321
```

Guarda. En la terminal del setup: `Ctrl+C`.

Arranca en serio:

```bash
cd ~/Desktop/tesla-familia-bot
export SSL_CERT_FILE=$HOME/zscaler-chain.pem
python3 main.py --telegram
```

En el iPhone prueba, en este orden:

1. `hola` — debe decir live/demo y monitor ON
2. `estado` — batería / parked / odómetro (ya funciona en live)
3. `luces` — solo si el Y está en **P** y `tesla-http-proxy` está en `127.0.0.1:4443`
4. `carga` — estado del cargador
5. `ayuda` — lista completa

También puedes tocar **/** en el teclado de Telegram: sale el menú (`estado`, `luces`, …).

---

## Cómo lo usa otra persona de la familia

1. Tú le pasas el link `t.me/TuUserBot` (no el token).
2. Esa persona toca Start y escribe `hola`.
3. Si olvidaste su chat id, el bot **no** ejecutará `luces` / `desbloquear`. Te dirá que falta autorizar.
4. Arranca una vez `python3 main.py --telegram --setup`, que te escriba, copia el id nuevo, agrégalo a `TELEGRAM_CHAT_IDS`, reinicia sin `--setup`.

No publiques el link del bot en un grupo abierto. El allowlist es la defensa; el username igual se puede buscar.

---

## Qué tiene que estar prendido en el Mac

Para que el iPhone reciba respuesta:

| Pieza | Para qué |
|--------|----------|
| `python3 main.py --telegram` | Escucha Telegram y habla con Tesla |
| Docker `tesla-http-proxy` en `127.0.0.1:4443` | Comandos firmados: luces, lock, clima, carga XX |
| `.env` con token Tesla + refresh + VIN | Lecturas Fleet |
| Mac despierto | Si se duerme, el bot muere |

Para que no se duerma mientras pruebas:

```bash
caffeinate -i python3 main.py --telegram
```

Esto **no** es un servicio 24/7 todavía. Token Tesla caduca (~8 h) hasta que cerremos el issue de refresh automático. Si `estado` de repente falla con 401, hay que rotar el token otra vez.

---

## Comandos que la familia va a usar

| En Telegram | Qué hace | Requiere |
|-------------|----------|----------|
| `estado` | Snapshot | Solo lectura Fleet |
| `batería` / `rango` / `ubicación` | Lecturas | Solo lectura Fleet |
| `carga` | Estado del cargador | Lectura |
| `carga 80` | Límite 50–100 | Proxy + Virtual Key |
| `luces` | Flash | Proxy + auto en P |
| `clima` / `apagar clima` | Precondicionar | Proxy |
| `bloquear` / `desbloquear` | Puertas | Proxy |
| `ir a Unicentro` | Navegación | Proxy |
| `viajes` / `resumen` | Logs SQLite | Local |

App Tesla a usar: **523a361f-12e3-4f22-a95e-b71348948b51** (owner `mccepedap`).  
No uses la app `8176c514` — el dominio `danielvegac.github.io` ya está tomado por la 523.

---

## Si algo sale mal

**BotFather dice username ocupado**  
Prueba otro que termine en `bot`.

**El iPhone no recibe respuesta**  
El proceso del Mac no está corriendo, o `TELEGRAM_BOT_TOKEN` está mal (un espacio al pegar lo rompe).

**Responde el chat id pero no hace `estado`**  
Sigue en setup, o `TELEGRAM_CHAT_IDS` no coincide (copia mal, o escribiste desde otra cuenta).

**`luces` falla / “command protocol”**  
Proxy caído, Virtual Key no es la de `keys-owner`, o el auto no está en P.  
`docker ps` y `python3 -m tesla_client` en el Mac primero.

**Se filtró el token**  
BotFather → `/revoke` → pega el token nuevo en `.env` → reinicia.

**Quieres borrar el bot**  
BotFather → `/deletebot`. Irreversible. Crea otro con `/newbot`.

---

## Por qué no webhook

Webhook = Telegram llama a una URL `https://…` en tu casa. Eso pide IP pública, HTTPS y pelear con Zscaler.

Long poll = el Mac pregunta a Telegram “¿hay mensajes?” cada ~30 s. Feo, simple, suficiente para un bot familiar en un Mac de escritorio.
