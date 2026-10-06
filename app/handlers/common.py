from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User
from app.services import get_or_create_user
from app.keyboards import main_menu
from app.config import settings

router = Router()

def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids

@router.message(CommandStart())
async def start(message: Message):
    async with SessionLocal() as session:
        await get_or_create_user(session, message.from_user)
        await session.commit()
    await message.answer(
        "👋 Добро пожаловать в <b>StandKnife Tournaments</b>!\n\n"
        "Здесь можно участвовать в турнирах, получать Gold и создавать заявки на ручной вывод.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )

@router.callback_query(lambda c: c.data == "back_main")
async def back_main(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=main_menu(is_admin(call.from_user.id)))
    await call.answer()
