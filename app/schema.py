"""Добавляет недостающие колонки (create_all не меняет существующие таблицы)."""
from sqlalchemy import text
from app.db import engine


async def ensure_schema() -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason VARCHAR(500)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS side VARCHAR(2)",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS is_winner BOOLEAN DEFAULT FALSE",
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS winner_side VARCHAR(10)",
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS result_screenshot TEXT",
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS cover_photo TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_rewarded BOOLEAN DEFAULT FALSE",
        """CREATE TABLE IF NOT EXISTS bot_settings (
            key VARCHAR(64) PRIMARY KEY,
            value VARCHAR(255) DEFAULT ''
        )""",
    ]
    async with engine.begin() as conn:
        for sql in statements:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass
