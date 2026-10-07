from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(url: str) -> str:
    """asyncpg не понимает sslmode — меняем на ssl=require."""
    url = url.strip()
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # sslmode=require -> ssl=require; убрать channel_binding
    url = url.replace("sslmode=require", "ssl=require")
    url = url.replace("channel_binding=require", "")
    url = url.replace("&&", "&").replace("?&", "?").rstrip("&").rstrip("?")
    if "ssl=" not in url and "localhost" not in url and "127.0.0.1" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}ssl=require"
    return url


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
    if not admins:
        raise RuntimeError("ADMIN_IDS пуст")
    return Settings(
        token,
        _normalize_database_url(db),
        admins,
        os.getenv("TIMEZONE", "Europe/Moscow"),
    )


settings = load_settings()
