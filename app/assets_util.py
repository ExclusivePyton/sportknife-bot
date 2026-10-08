"""Пути к статичным картинкам бота."""
from pathlib import Path
from aiogram.types import FSInputFile

_DIR = Path(__file__).resolve().parent / "assets"


def asset(name: str) -> FSInputFile | None:
    path = _DIR / name
    if path.is_file():
        return FSInputFile(path)
    return None
