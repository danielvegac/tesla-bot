"""Telegram process-start lines. Tesla-app tone: short, no tutorial."""

# Change TELEGRAM_STARTUP_STYLE in .env: quiet | app | valet | presence | studio
STYLES = {
    "quiet": "En línea.",
    "app": "Model Y · en línea.",
    "valet": "Listo cuando tú lo estés.",
    "presence": "Aquí.",
    "studio": "Buenas. El Y está a un mensaje.",
}
DEFAULT = "app"


def hello(style: str | None = None) -> str:
    key = (style or DEFAULT).strip().lower()
    return STYLES.get(key, STYLES[DEFAULT])
