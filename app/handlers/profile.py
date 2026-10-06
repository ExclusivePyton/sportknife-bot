from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User
from app.services import get_or_create_user, available_balance
from app.keyboards import back_kb, profile_edit_kb
from app.states import ProfileStates

router = Router()

@router.message(F.text == "👤 Профиль")
async def profile(message: Message):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        await s.commit()
        await message.answer(
            f"👤 <b>Профиль</b>\n\n🆔 Telegram ID: <code>{u.telegram_id}</code>\n"
            f"👤 Username: @{u.username or 'не указан'}\n🎮 Game ID: {u.game_id or 'не указан'}\n"
            f"🏷 NickName: {u.nickname or 'не указан'}\n🪙 Баланс: {u.balance} Gold\n"
            f"🔒 Зарезервировано: {u.reserved_balance} Gold\n"
            f"💰 Доступно: {available_balance(u)} Gold",
            reply_markup=profile_edit_kb()
        )
    await message.answer("Чтобы изменить данные профиля, отправьте:\n<code>Game ID</code> или используйте кнопку ниже.", reply_markup=None)


@router.callback_query(lambda c: c.data == "profile:game")
async def profile_game(call: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.game_id)
    await call.message.answer("🎮 Введите Game ID:")
    await call.answer()

@router.callback_query(lambda c: c.data == "profile:nick")
async def profile_nick(call: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.nickname)
    await call.message.answer("🏷 Введите NickName:")
    await call.answer()

@router.message(ProfileStates.game_id)
async def save_game_id(message: Message, state: FSMContext):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        u.game_id = message.text.strip()
        await s.commit()
    await state.clear()
    await message.answer("✅ Game ID сохранён.")

@router.message(F.text.startswith("Game ID:"))
async def set_game_id(message: Message, state: FSMContext):
    await state.update_data(game_id=message.text.split(":",1)[1].strip())
    await state.set_state(ProfileStates.nickname)
    await message.answer("Теперь отправьте NickName.")

@router.message(ProfileStates.nickname)
async def save_nickname(message: Message, state: FSMContext):
    data = await state.get_data()
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        u.game_id = data["game_id"]
        u.nickname = message.text.strip()
        await s.commit()
    await state.clear()
    await message.answer("✅ Профиль обновлён.")
