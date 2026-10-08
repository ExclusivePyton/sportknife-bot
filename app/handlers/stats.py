from aiogram import Router, F
from aiogram.types import Message
from app.db import SessionLocal
from app.services import get_or_create_user
from app.keyboards import main_menu
from app.config import settings

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


@router.message(F.text == "📊 Статистика")
async def stats(message: Message):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        await s.commit()
    played = u.tournaments_played or 0
    wins = u.wins or 0
    winrate = f"{(wins / played * 100):.0f}%" if played else "—"
    text = (
        "📊 <b>Ваша статистика</b>\n\n"
        f"🎮 Game ID: <code>{u.game_id or 'не указан'}</code>\n"
        f"🏷 Ник: {u.nickname or '—'}\n\n"
        f"🏆 Сыграно турниров: <b>{played}</b>\n"
        f"🥇 Побед: <b>{wins}</b>\n"
        f"📈 Винрейт: <b>{winrate}</b>\n\n"
        f"💰 Всего заработано: <b>{u.total_earned}</b> Gold\n"
        f"💸 Выведено: <b>{u.total_withdrawn}</b> Gold\n"
        f"🪙 Сейчас на балансе: <b>{u.balance}</b> Gold"
    )
    await message.answer(text, reply_markup=main_menu(is_admin(message.from_user.id)))
