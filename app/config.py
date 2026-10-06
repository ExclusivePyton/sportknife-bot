from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: tuple[int, ...]
    timezone: str = "Europe/Moscow"

def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    db = os.getenv("DATABASE_URL", "").strip()
    admins_raw = os.getenv("ADMIN_IDS", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан")
    if not db:
        raise RuntimeError("DATABASE_URL не задан")
    if not admins_raw:
        raise RuntimeError("ADMIN_IDS не задан")
    try:
        admins = tuple(int(x.strip()) for x in admins_raw.split(",") if x.strip())
    except ValueError as e:
        raise RuntimeError("ADMIN_IDS должен содержать Telegram ID через запятую") from e
    return Settings(token, db, admins, os.getenv("TIMEZONE", "Europe/Moscow"))

settings = load_settings()
