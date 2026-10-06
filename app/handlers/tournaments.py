from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import Tournament, Registration, TournamentStatus
from app.services import get_or_create_user, create_registration
from app.keyboards import tournament_list, tournament_detail, main_menu
from app.config import settings

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


async def render_tour(tid, uid):
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
        if not t:
            return "Турнир не найден.", False
        count = (
            await s.execute(
                select(func.count(Registration.id)).where(Registration.tournament_id == tid)
            )
        ).scalar_one()
        reg = (
            await s.execute(
                select(Registration.id).where(
                    Registration.tournament_id == tid, Registration.user_id == uid
                )
            )
        ).scalar_one_or_none()
        cost = "Бесплатно" if t.registration_cost == 0 else f"{t.registration_cost} Gold"
        reg_status = "открыта" if t.registration_open else "закрыта"
        text = (
            f"🏆 <b>{t.title}</b>\n\n{t.description}\n\n📅 {t.start_at:%d.%m.%Y %H:%M}\n"
            f"🎮 Формат: {t.format}\n👥 Участники: {count}/{t.max_participants}\n"
            f"🪙 Стоимость регистрации: {cost}\n🏅 Призы: {t.prize_fund}\n"
            f"📜 Условия: {t.conditions}\n"
            f"ℹ️ {t.additional_info or '—'}\n\nСтатус: {t.status.value}\nРегистрация: {reg_status}"
        )
        return text, bool(reg)


@router.message(F.text == "🏆 Турниры")
async def tournaments(message: Message):
    async with SessionLocal() as s:
        items = (
            await s.execute(
                select(Tournament)
                .where(Tournament.status.in_([TournamentStatus.open, TournamentStatus.running]))
                .order_by(Tournament.start_at)
            )
        ).scalars().all()
    if not items:
        await message.answer(
            "🏆 Сейчас доступных турниров нет.",
            reply_markup=main_menu(is_admin(message.from_user.id)),
        )
        return
    await message.answer(
        "🏆 <b>Доступные турниры</b>\nВыберите турнир:",
        reply_markup=tournament_list(items),
    )

@router.callback_query(lambda c: c.data == "tours")
async def tours_cb(call: CallbackQuery):
    async with SessionLocal() as s:
        items = (await s.execute(select(Tournament).where(Tournament.status.in_([TournamentStatus.open, TournamentStatus.running])).order_by(Tournament.start_at))).scalars().all()
    await call.message.edit_text("🏆 <b>Доступные турниры</b>", reply_markup=tournament_list(items))
    await call.answer()

@router.callback_query(lambda c: c.data.startswith("tour:"))
async def tour_detail_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        text, registered = await render_tour(tid, u.id)
    await call.message.edit_text(text, reply_markup=tournament_detail(tid, registered))
    await call.answer()

@router.callback_query(lambda c: c.data.startswith("reg:"))
async def register_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        if not u.game_id:
            await s.commit()
            await call.answer("Сначала укажите Game ID через /start", show_alert=True)
            return
        try:
            await create_registration(s, u.id, tid)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            return
    await call.answer("Регистрация успешна!", show_alert=True)
    text, registered = await render_tour(tid, u.id)
    await call.message.edit_text(text, reply_markup=tournament_detail(tid, registered))
