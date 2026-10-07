"""История пополнений и выводов (раньше здесь была вкладка «Gold»)."""
from html import escape

from aiogram import Router, F
from aiogram.types import Message

from app.db import SessionLocal
from app.services import get_or_create_user, available_balance, get_history
from app.timeutil import format_msk

router = Router()

WD_STATUS = {"pending": "🟡 В обработке", "paid": "🟢 Выплачено", "rejected": "🔴 Отклонено"}


# «🪙 Gold» и «📜 История выводов» оставлены для старых клавиатур, которые ещё висят у игроков
@router.message(F.text.in_({"📜 История", "📜 История выводов", "🪙 Gold"}))
async def history(message: Message):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        deposits, withdrawals = await get_history(s, u.id)
        await s.commit()

    text = (
        "📜 <b>История пополнений и выводов</b>\n\n"
        f"💰 Доступно: <b>{available_balance(u)}</b> Gold"
        f" (🔒 в резерве: {u.reserved_balance})\n\n"
        "📥 <b>Пополнения</b>\n"
    )
    if deposits:
        for d in deposits:
            text += f"🟢 +{d.amount} Gold — {escape(d.description)}\n🕒 {format_msk(d.created_at)} (МСК)\n\n"
    else:
        text += "Пополнений пока нет.\n\n"

    text += "📤 <b>Выводы</b>\n"
    if withdrawals:
        for w in withdrawals:
            text += (
                f"{WD_STATUS.get(w.status.value, w.status.value)} #{w.id} — {w.amount} Gold\n"
                f"🔫 {escape(w.skin_name)} | Pattern: {escape(w.pattern)}\n"
                f"🕒 {format_msk(w.created_at)} (МСК)\n\n"
            )
    else:
        text += "Выводов пока нет."

    if len(text) > 4000:
        text = text[:3990] + "…"
    await message.answer(text)
