from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.db import SessionLocal
from app.services import (
    get_or_create_user,
    is_game_id_taken,
    try_complete_referral,
    get_referral_reward,
    count_referrals,
)
from app.keyboards import main_menu, subscription_kb, SUPPORT_USERNAME
from app.config import settings
from app.states import StartGameIdStates
from app.middlewares import check_subscriptions

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


def valid_game_id(text: str) -> bool:
    return text.isdigit() and len(text) == 8


def parse_ref_payload(text: str | None) -> int | None:
    """Из /start ref123456 или /start ref_123456 → telegram_id."""
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if payload.startswith("ref_"):
        payload = payload[4:]
    elif payload.startswith("ref"):
        payload = payload[3:]
    if payload.isdigit():
        return int(payload)
    return None


async def maybe_pay_referral(bot, session, user) -> None:
    """Начислить реферальную награду, если условия выполнены (подписка уже проверена)."""
    if not user or not user.referred_by_id or user.referral_rewarded:
        return
    if not user.game_id:
        return
    ok, amount, ref_tg = await try_complete_referral(session, user.id)
    if not ok:
        return
    await session.commit()
    if ref_tg and amount > 0:
        try:
            await bot.send_message(
                ref_tg,
                f"🎉 Вам начислено <b>{amount}</b> Gold за приглашённого друга!\n"
                f"(он подписался на канал и зарегистрировался в боте)",
            )
        except Exception:
            pass


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    ref_tid = parse_ref_payload(message.text)

    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user, referrer_telegram_id=ref_tid)
        await session.commit()
        # refresh attributes
        reward = await get_referral_reward(session)

    if not is_admin(message.from_user.id):
        missing = await check_subscriptions(message.bot, message.from_user.id)
        if missing:
            await message.answer(
                "🔒 Чтобы пользоваться ботом, подпишитесь на каналы ниже.\n\n"
                "После подписки нажмите «✅ Я подписался».\n"
                "Это нужно и для реферальной награды пригласившему.",
                reply_markup=subscription_kb(missing),
            )
            return

    if not user.game_id:
        await state.set_state(StartGameIdStates.waiting)
        await message.answer(
            "⚔️ <b>StandKnife Tournaments</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Добро пожаловать!\n\n"
            "Укажите свой <b>игровой ID</b> (ровно <b>8 цифр</b>).\n\n"
            "⚠️ После сохранения изменить ID нельзя."
        )
        return

    # подписка + game_id — пробуем закрыть реферала
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user)
        await maybe_pay_referral(message.bot, session, user)

    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref{message.from_user.id}"
    await message.answer(
        "⚔️ <b>StandKnife Tournaments</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🎮 Game ID: <code>{user.game_id}</code>\n\n"
        f"👥 Реферальная ссылка (за друга +{reward} Gold после его подписки):\n"
        f"<code>{link}</code>\n\n"
        "Выберите раздел в меню ниже 👇",
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
        if await is_game_id_taken(session, text):
            await message.answer(
                "❌ Этот Game ID уже занят другим игроком. Введите свой:"
            )
            return
        user.game_id = text
        await session.commit()

        # после game_id — если уже подписан, начислить реф
        missing = []
        if not is_admin(message.from_user.id):
            missing = await check_subscriptions(message.bot, message.from_user.id)
        if not missing:
            await maybe_pay_referral(message.bot, session, user)

    await state.clear()
    await message.answer(
        f"✅ Game ID <code>{text}</code> сохранён.\n\n"
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

        if user.game_id:
            await maybe_pay_referral(call.bot, session, user)

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


@router.message(F.text.in_({"👥 Рефералы", "👥 Реф. программа"}))
async def referral_info(message: Message):
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref{message.from_user.id}"
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user)
        reward = await get_referral_reward(session)
        total, done = await count_referrals(session, user.id)
        await session.commit()
    await message.answer(
        "👥 <b>Реферальная программа</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"За каждого друга, который:\n"
        f"1) перейдёт по <b>вашей ссылке</b>\n"
        f"2) подпишется на обязательный канал\n"
        f"3) укажет Game ID в боте\n\n"
        f"вы получите <b>{reward}</b> Gold.\n\n"
        f"📊 Приглашено: <b>{total}</b> · Награда начислена: <b>{done}</b>\n\n"
        f"🔗 Ваша ссылка:\n<code>{link}</code>",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )


@router.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery):
    from app import live
    live.untrack(call.message.chat.id, call.message.message_id)
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
@router.message(F.text.in_({"❌ Отмена", "Отмена", "отмена"}))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )


@router.message(F.text.in_({"📖 Правила", "📖 Помощь", "/help"}))
async def help_msg(message: Message):
    await message.answer(
        "📖 <b>Правила StandKnife Tournaments</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "<b>Запрещено:</b>\n"
        "• использование читов, багов и стороннего ПО в игре\n"
        "• абуз Gold, накрутка, мультиаккаунты ради наград\n"
        "• передача аккаунта / Game ID другим лицам\n"
        "• оскорбления, токсичность, срыв турниров\n"
        "• фейковые скриншоты и обман администрации\n"
        "• абуз реферальной системы (накрутка приглашений)\n\n"
        "<b>Наказание:</b> бан в боте без возврата Gold, "
        "дисквалификация с турниров.\n\n"
        "<b>Как играть:</b>\n"
        "1) Подписка на каналы\n"
        "2) Game ID (8 цифр)\n"
        "3) Регистрация на турнир (сторона Т / КТ)\n"
        "4) Старт → ждут инвайт в лобби в игре\n"
        "5) Админ завершает матч и выдаёт призы\n\n"
        "💸 Мин. вывод: <b>2500</b> Gold (одна заявка в обработке)\n"
        "👥 Рефералы — кнопка «Рефералы» в меню\n\n"
        f"💬 Поддержка: @{SUPPORT_USERNAME}"
    )
