"""Московское время для ввода и отображения."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def parse_msk(text: str) -> datetime:
    """Разобрать 'ДД.ММ.ГГГГ ЧЧ:ММ' как московское время."""
    dt = datetime.strptime(text.strip(), "%d.%m.%Y %H:%M")
    return dt.replace(tzinfo=MSK)


def format_msk(dt: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Показать дату/время по Москве."""
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime(fmt)


def now_msk() -> datetime:
    return datetime.now(MSK)
