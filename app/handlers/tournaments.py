from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import Tournament, Registration, TournamentStatus
from app.services import get_or_create_user, create_registration, cancel_registration
from app.keyboards import tournament_list, tournament_detail, main_menu
from app.config import settings
from app.timeutil import format_msk

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


async def render_tour(tid, uid):
    """text, registered, can_leave"""
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
        if not t:
            return "Турнир не найден.", False, False
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
        registered = bool(reg)
        can_leave = registered and t.status == TournamentStatus.open
        text = (
            f"🏆 <b>{t.title}</b>\n\n{t.description}\n\n"
            f"📅 Старт: когда наберётся полный состав\n"
            f"🎮 Формат: {t.format}\n👥 Слоты: {count}/{t.max_participants}\n"
            f"🪙 Стоимость регистрации: {cost}\n🏅 Призы: {t.prize_fund}\n"
            f"📜 Условия: {t.conditions}\n"
            f"ℹ️ {t.additional_info or '—'}\n\n"
            f"Статус: {t.status.value}\nРегистрация: {reg_status}"
        )
        return text, registered, can_leave


@router.message(F.text == "🏆 Турниры")
async def tournaments(message: Message):
    async with SessionLocal() as s:
        items = (
            await s.execute(
                select(Tournament)
                .where(Tournament.status.in_([TournamentStatus.open, TournamentStatus.running]))
                .order_by(Tournament.id.desc())
            )
        ).scalars().all()
        counts = {}
        for t in items:
            counts[t.id] = (
                await s.execute(
                    select(func.count(Registration.id)).where(Registration.tournament_id == t.id)
                )
            ).scalar_one()
    if not items:
        await message.answer(
            "🏆 Сейчас доступных турниров нет.",
            reply_markup=main_menu(is_admin(message.from_user.id)),
        )
        return
    await message.answer(
        "🏆 <b>Доступные турниры</b>\nВыберите турнир:",
        reply_markup=tournament_list(items, counts),
    )


@router.callback_query(lambda c: c.data == "tours")
async def tours_cb(call: CallbackQuery):
    async with SessionLocal() as s:
        items = (
            await s.execute(
                select(Tournament)
                .where(Tournament.status.in_([TournamentStatus.open, TournamentStatus.running]))
                .order_by(Tournament.id.desc())
            )
        ).scalars().all()
        counts = {}
        for _t in items:
            counts[_t.id] = (
                await s.execute(
                    select(func.count(Registration.id)).where(Registration.tournament_id == _t.id)
                )
            ).scalar_one()
    await call.message.edit_text(
        "🏆 <b>Доступные турниры</b>",
        reply_markup=tournament_list(items, counts),
    )
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("tour:"))
async def tour_detail_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        await s.commit()
    text, registered, can_leave = await render_tour(tid, u.id)
    await call.message.edit_text(
        text,
        reply_markup=tournament_detail(tid, registered, can_leave),
    )
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
        filled = False
        try:
            result = await create_registration(s, u.id, tid)
            if isinstance(result, tuple):
                _, filled = result
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            return
        uid = u.id
    msg = "Регистрация успешна!"
    if filled:
        msg = "Регистрация успешна! Состав набран — регистрация закрыта."
    await call.answer(msg, show_alert=True)
    text, registered, can_leave = await render_tour(tid, uid)
    await call.message.edit_text(
        text,
        reply_markup=tournament_detail(tid, registered, can_leave),
    )
    if filled:
        # уведомить всех участников
        from app.services import list_tournament_participant_ids
        async with SessionLocal() as s:
            ids = await list_tournament_participant_ids(s, tid)
            t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
            title = t.title if t else str(tid)
        import asyncio
        note = (
            f"🏁 Состав турнира <b>{title}</b> набран!\n"
            "Регистрация закрыта. Ожидайте старта от администратора."
        )
        for tg_id in ids:
            try:
                await call.bot.send_message(tg_id, note)
            except Exception:
                pass
            await asyncio.sleep(0.03)


@router.callback_query(lambda c: c.data.startswith("unreg:"))
async def unregister_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        reopened = False
        try:
            result = await cancel_registration(s, u.id, tid)
            if isinstance(result, tuple):
                refund, reopened = result
            else:
                refund = result
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            return
        uid = u.id
    msg = "Вы вышли из турнира."
    if refund and refund > 0:
        msg += f" Возвращено {refund} Gold."
    if reopened:
        msg += " Регистрация снова открыта."
    await call.answer(msg, show_alert=True)
    text, registered, can_leave = await render_tour(tid, uid)
    await call.message.edit_text(
        text,
        reply_markup=tournament_detail(tid, registered, can_leave),
    )
