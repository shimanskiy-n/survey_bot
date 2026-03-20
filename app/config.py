import os
from dataclasses import dataclass


@dataclass
class Settings:
    bot_token: str
    db_path: str = "bot.db"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Установите её перед запуском бота."
        )
    return Settings(bot_token=token)

