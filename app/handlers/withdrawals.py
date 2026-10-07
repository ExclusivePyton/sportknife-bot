from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.db import SessionLocal
from app.models import Withdrawal
from app.services import get_or_create_user, create_withdrawal
from app.states import WithdrawalStates

router = Router()

@router.message(F.text == "💸 Вывод")
async def withdraw_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(WithdrawalStates.amount)
    await message.answer("💸 Введите количество Gold для вывода:")

@router.message(WithdrawalStates.amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("Введите положительное число.")
        return
    await state.update_data(amount=amount)
    await state.set_state(WithdrawalStates.skin)
    await message.answer("🔫 Введите точное название скина:")

@router.message(WithdrawalStates.skin)
async def wd_skin(message: Message, state: FSMContext):
    await state.update_data(skin=message.text.strip())
    await state.set_state(WithdrawalStates.pattern)
    await message.answer("🎨 Введите Pattern (обязательно):")

@router.message(WithdrawalStates.pattern)
async def wd_pattern(message: Message, state: FSMContext):
    if not message.text.strip():
        await message.answer("Pattern обязателен.")
        return
    await state.update_data(pattern=message.text.strip())
    await state.set_state(WithdrawalStates.screenshot)
    await message.answer("📸 Отправьте скриншот рынка StandKnife, где видно именно этот скин:")

@router.message(WithdrawalStates.screenshot, F.photo)
async def wd_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(screenshot=message.photo[-1].file_id)
    await state.set_state(WithdrawalStates.confirm)
    await message.answer(
        f"💸 <b>Заявка на вывод</b>\n\n🪙 Сумма: {data['amount']} Gold\n"
        f"🔫 Скин: {data['skin']}\n🎨 Pattern: {data['pattern']}\n📸 Скриншот: прикреплён\n\n"
        "После подтверждения данные заявки изменить нельзя.\n\n"
        "Для создания заявки отправьте: <code>ПОДТВЕРДИТЬ</code>\nДля отмены: <code>ОТМЕНА</code>"
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
            wd = await create_withdrawal(s, u.id, data["amount"], data["skin"], data["pattern"], data["screenshot"])
            await s.commit()
        except Exception as e:
            await s.rollback()
            await message.answer(f"❌ Не удалось создать заявку: {e}")
            return
    await state.clear()
    await message.answer(f"✅ Заявка #{wd.id} создана.\n🟡 Статус: В обработке\n🔒 Gold зарезервирован.")
