from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Transaction
from app.services import get_or_create_user, available_balance

router = Router()

@router.message(F.text == "🪙 Gold")
async def gold(message: Message):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        txs = (await s.execute(select(Transaction).where(Transaction.user_id == u.id).order_by(Transaction.created_at.desc()).limit(10))).scalars().all()
        await s.commit()
    text = f"🪙 <b>Gold</b>\n\nБаланс: {u.balance} Gold\n🔒 В резерве: {u.reserved_balance} Gold\n💰 Доступно: {available_balance(u)} Gold\n\n<b>Последние операции:</b>\n"
    for x in txs:
        sign = "+" if x.amount > 0 else ""
        text += f"{sign}{x.amount} — {x.description}\n"
    await message.answer(text)
