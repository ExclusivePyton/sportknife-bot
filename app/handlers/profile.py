from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.db import SessionLocal
from app.services import get_or_create_user, available_balance
from app.keyboards import profile_edit_kb
from app.states import ProfileStates

router = Router()


@router.message(F.text == "👤 Профиль")
async def profile(message: Message):
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        await s.commit()
    await message.answer(
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 Telegram ID: <code>{u.telegram_id}</code>\n"
        f"👤 Username: @{u.username or 'не указан'}\n"
        f"🎮 Game ID: <code>{u.game_id or 'не указан'}</code>\n"
        f"🏷 NickName: {u.nickname or 'не указан'}\n"
        f"🪙 Баланс: {u.balance} Gold\n"
        f"🔒 Зарезервировано: {u.reserved_balance} Gold\n"
        f"💰 Доступно: {available_balance(u)} Gold\n\n"
        f"{'⚠️ Game ID задаётся один раз и не меняется.' if u.game_id else 'Укажите Game ID через /start'}",
        reply_markup=profile_edit_kb(can_edit_game_id=False),
    )


@router.callback_query(F.data == "profile:game")
async def profile_game(call: CallbackQuery):
    await call.answer(
        "Game ID нельзя изменить после первого сохранения.",
        show_alert=True,
    )


@router.callback_query(F.data == "profile:nick")
async def profile_nick(call: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.nickname)
    await call.message.answer("🏷 Введите NickName:")
    await call.answer()


@router.message(ProfileStates.nickname)
async def save_nickname(message: Message, state: FSMContext):
    nick = (message.text or "").strip()
    if not nick or len(nick) > 64:
        await message.answer("Введите ник от 1 до 64 символов.")
        return
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        u.nickname = nick
        await s.commit()
    await state.clear()
    await message.answer(f"✅ NickName сохранён: <b>{nick}</b>")
