"""Добавляет недостающие колонки (create_all не меняет существующие таблицы)."""
from sqlalchemy import text
from app.db import engine


async def ensure_schema() -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason VARCHAR(500)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ",
    ]
    async with engine.begin() as conn:
        for sql in statements:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass
