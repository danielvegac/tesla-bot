"""Optional WhatsApp stub (Telegram is the primary notifier for now)."""


class WhatsAppBot:
    async def send_message(self, message: str) -> bool:
        print(f"[WhatsApp/stub] → {message}")
        return True
