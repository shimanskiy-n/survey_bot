import os
from dataclasses import dataclass


@dataclass
class Settings:
    bot_token: str
    db_path: str = "bot.db"
    admin_telegram_id: int | None = None


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Установите её перед запуском бота."
        )

    admin_telegram_id_raw = os.getenv("ADMIN_TELEGRAM_ID")
    admin_telegram_id: int | None = None
    if admin_telegram_id_raw:
        try:
            admin_telegram_id = int(admin_telegram_id_raw)
        except ValueError as e:
            raise RuntimeError(
                "Переменная окружения ADMIN_TELEGRAM_ID должна быть числом."
            ) from e

    return Settings(
        bot_token=token,
        admin_telegram_id=admin_telegram_id,
    )

