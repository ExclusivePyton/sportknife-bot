from aiogram import Router, F
from aiogram.types import Message
from app.db import SessionLocal
from app.services import get_or_create_user, available_balance

router = Router()

@router.message(F.text == "📊 Статистика")
async def stats(message: Message):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        await s.commit()
    await message.answer(
        f"📊 <b>Моя статистика</b>\n\n🏆 Турниров сыграно: {u.tournaments_played}\n"
        f"🥇 Побед: {u.wins}\n🥈 Вторых мест: {u.second_places}\n🥉 Третьих мест: {u.third_places}\n"
        f"🪙 Всего заработано: {u.total_earned} Gold\n💸 Всего выведено: {u.total_withdrawn} Gold\n"
        f"💰 Текущий баланс: {u.balance} Gold\n🔒 Gold в обработке: {u.reserved_balance} Gold\n"
        f"🟢 Доступно: {available_balance(u)} Gold"
    )
