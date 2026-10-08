from html import escape

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.db import SessionLocal
from app.services import get_or_create_user, create_withdrawal
from app.states import WithdrawalStates
from app.keyboards import withdrawal_actions

router = Router()


@router.message(F.text == "💸 Вывод")
async def withdraw_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(WithdrawalStates.amount)
    await message.answer(
        "💸 Введите сумму вывода в Gold\n"
        "(минимум <b>2500</b>, одна заявка в обработке):"
    )


@router.message(WithdrawalStates.amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число.")
        return
    await state.update_data(amount=amount)
    await state.set_state(WithdrawalStates.skin)
    await message.answer("🔫 Введите точное название скина:")


@router.message(WithdrawalStates.skin)
async def wd_skin(message: Message, state: FSMContext):
    await state.update_data(skin=(message.text or "").strip())
    await state.set_state(WithdrawalStates.pattern)
    await message.answer("🎨 Введите Pattern (обязательно):")


@router.message(WithdrawalStates.pattern)
async def wd_pattern(message: Message, state: FSMContext):
    if not (message.text or "").strip():
        await message.answer("Pattern обязателен.")
        return
    await state.update_data(pattern=message.text.strip())
    await state.set_state(WithdrawalStates.screenshot)
    await message.answer(
        "📸 Отправьте скриншот рынка StandKnife, где видно именно этот скин:"
    )


@router.message(WithdrawalStates.screenshot, F.photo)
async def wd_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(screenshot=message.photo[-1].file_id)
    await state.set_state(WithdrawalStates.confirm)
    await message.answer(
        f"💸 <b>Заявка на вывод</b>\n\n"
        f"🪙 Сумма: {data['amount']} Gold\n"
        f"🔫 Скин: {escape(str(data['skin']))}\n"
        f"🎨 Pattern: {escape(str(data['pattern']))}\n"
        f"📸 Скриншот: прикреплён\n\n"
        "После подтверждения данные заявки изменить нельзя.\n\n"
        "Для создания заявки отправьте: <code>ПОДТВЕРДИТЬ</code>\n"
        "Для отмены: <code>ОТМЕНА</code>"
    )


@router.message(WithdrawalStates.screenshot)
async def wd_need_photo(message: Message):
    await message.answer("Нужен именно скриншот-фотография. Отправьте его как фото Telegram.")


@router.message(WithdrawalStates.confirm, F.text.casefold() == "отмена")
async def wd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Заявка отменена.")


@router.message(WithdrawalStates.confirm, F.text.casefold() == "подтвердить")
async def wd_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        try:
            wd = await create_withdrawal(
                s, u.id, data["amount"], data["skin"], data["pattern"], data["screenshot"]
            )
            await s.commit()
        except Exception as e:
            await s.rollback()
            await message.answer(f"❌ Не удалось создать заявку: {e}")
            return
        # данные для уведомления админам
        wd_id = wd.id
        amount = wd.amount
        skin = wd.skin_name
        pattern = wd.pattern
        shot = wd.screenshot_file_id
        nick = u.nickname or u.username or "—"
        game_id = u.game_id or "—"
        tg_id = u.telegram_id

    await state.clear()
    await message.answer(
        f"✅ Заявка #{wd_id} создана.\n"
        f"🟡 Статус: В обработке\n"
        f"🔒 Gold зарезервирован."
    )

    # уведомление всем администраторам
    caption = (
        f"🔔 <b>Новая заявка на вывод #{wd_id}</b>\n\n"
        f"👤 {escape(str(nick))}\n"
        f"🎮 Game ID: <code>{escape(str(game_id))}</code>\n"
        f"🆔 Telegram: <code>{tg_id}</code>\n"
        f"🪙 Сумма: <b>{amount}</b> Gold\n"
        f"🔫 Скин: {escape(str(skin))}\n"
        f"🎨 Pattern: {escape(str(pattern))}"
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_photo(
                admin_id,
                shot,
                caption=caption,
                reply_markup=withdrawal_actions(wd_id),
            )
        except Exception:
            try:
                await message.bot.send_message(
                    admin_id,
                    caption + "\n\n(скриншот не удалось отправить)",
                    reply_markup=withdrawal_actions(wd_id),
                )
            except Exception:
                pass
