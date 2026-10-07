from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.db import SessionLocal
from app.services import get_or_create_user
from app.keyboards import main_menu, subscription_kb, SUPPORT_USERNAME
from app.config import settings
from app.states import StartGameIdStates
from app.middlewares import check_subscriptions

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


def valid_game_id(text: str) -> bool:
    return text.isdigit() and len(text) == 8


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user)
        await session.commit()

    if not is_admin(message.from_user.id):
        missing = await check_subscriptions(message.bot, message.from_user.id)
        if missing:
            await message.answer(
                "🔒 Чтобы пользоваться ботом, подпишитесь на каналы ниже.\n\n"
                "После подписки нажмите «✅ Я подписался».",
                reply_markup=subscription_kb(missing),
            )
            return

    if not user.game_id:
        await state.set_state(StartGameIdStates.waiting)
        await message.answer(
            "👋 Добро пожаловать в <b>StandKnife Tournaments</b>!\n\n"
            "Для начала укажите свой <b>игровой ID</b>.\n"
            "Он должен состоять <b>ровно из 8 цифр</b>.\n\n"
            "⚠️ После сохранения <b>изменить ID будет нельзя</b>."
        )
        return

    await message.answer(
        "👋 С возвращением в <b>StandKnife Tournaments</b>!\n\n"
        f"🎮 Ваш Game ID: <code>{user.game_id}</code>",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )


@router.message(StartGameIdStates.waiting)
async def save_start_game_id(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not valid_game_id(text):
        await message.answer(
            "❌ Game ID должен состоять <b>ровно из 8 цифр</b>. Попробуйте ещё раз:"
        )
        return
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user)
        if user.game_id:
            await state.clear()
            await message.answer(
                f"Game ID уже задан: <code>{user.game_id}</code>",
                reply_markup=main_menu(is_admin(message.from_user.id)),
            )
            return
        user.game_id = text
        await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Game ID <code>{text}</code> сохранён. Изменить его больше нельзя.\n\n"
        "Можете пользоваться ботом.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )


@router.callback_query(F.data == "check_sub")
async def check_sub_cb(call: CallbackQuery, state: FSMContext):
    missing = await check_subscriptions(call.bot, call.from_user.id)
    if missing:
        await call.message.answer(
            "❌ Вы ещё не подписаны на все каналы. Подпишитесь и нажмите кнопку снова.",
            reply_markup=subscription_kb(missing),
        )
        await call.answer("Подписка не полная", show_alert=True)
        return

    await call.answer("Подписка подтверждена ✅")
    async with SessionLocal() as session:
        user = await get_or_create_user(session, call.from_user)
        await session.commit()

    if not user.game_id:
        await state.set_state(StartGameIdStates.waiting)
        await call.message.answer(
            "✅ Подписка есть!\n\n"
            "Теперь укажите свой <b>игровой ID</b> (ровно 8 цифр).\n"
            "⚠️ После сохранения изменить его будет нельзя."
        )
        return

    await call.message.answer(
        "✅ Отлично! Можете пользоваться ботом.",
        reply_markup=main_menu(is_admin(call.from_user.id)),
    )


@router.message(F.text == "💬 Поддержка")
async def support(message: Message):
    await message.answer(
        "💬 По вопросам поддержки пишите:\n"
        f"👉 @{SUPPORT_USERNAME}\n\n"
        f'<a href="https://t.me/{SUPPORT_USERNAME}">Открыть чат с поддержкой</a>'
    )


@router.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "Главное меню:",
        reply_markup=main_menu(is_admin(call.from_user.id)),
    )
    await call.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )
