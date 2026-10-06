from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app.db import SessionLocal
from app.services import get_or_create_user, redeem_promo
from app.states import PromoRedeemStates
from app.keyboards import main_menu
from app.config import settings

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


@router.message(F.text == "🎁 Промокод")
async def promo_start(message: Message, state: FSMContext):
    await state.set_state(PromoRedeemStates.code)
    await message.answer(
        "🎁 Введите промокод:\n\n"
        "Можно отменить командой /cancel"
    )


@router.message(F.text == "/cancel")
async def cancel_any(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        return
    await state.clear()
    await message.answer(
        "Отменено.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )


@router.message(PromoRedeemStates.code)
async def promo_redeem(message: Message, state: FSMContext):
    code = (message.text or "").strip()
    if not code:
        await message.answer("Введите промокод текстом.")
        return
    async with SessionLocal() as s:
        user = await get_or_create_user(s, message.from_user)
        try:
            promo = await redeem_promo(s, user.id, code)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await message.answer(f"❌ {e}")
            return
    await state.clear()
    await message.answer(
        f"✅ Промокод <b>{promo.code}</b> активирован!\n"
        f"Начислено: <b>{promo.gold_amount}</b> Gold.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )
