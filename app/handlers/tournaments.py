import asyncio
from html import escape

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from app.db import SessionLocal
from app.models import Tournament, Registration, TournamentStatus, User
from app.services import (
    get_or_create_user, create_registration, cancel_registration, change_side,
    side_caps, count_by_side, SIDE_SHORT, list_tournament_participant_ids,
)
from app.keyboards import (
    tournament_list, finished_list, tournament_detail, side_pick_kb, main_menu,
)
from app.config import settings
from app import live
from app.assets_util import asset

router = Router()

STATUS_TEXT = {
    TournamentStatus.open: "открыт",
    TournamentStatus.running: "идёт",
    TournamentStatus.finished: "завершён",
    TournamentStatus.cancelled: "отменён",
}


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admin_ids


def _nick(r: Registration) -> str:
    return escape(r.nickname or "—")


async def render_list():
    """Текст и клавиатура списка актуальных турниров (с живыми счётчиками)."""
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
    text = "🏆 <b>Доступные турниры</b>\nВыберите турнир:" if items else "🏆 Сейчас активных турниров нет."
    return text, tournament_list(items, counts)


async def _load(tid, uid):
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
        if not t:
            return None
        regs = (
            await s.execute(
                select(Registration).where(Registration.tournament_id == tid).order_by(Registration.created_at, Registration.id)
            )
        ).scalars().all()
    mine = next((r for r in regs if r.user_id == uid), None)
    return t, regs, mine


def _participants_block(t, regs) -> str:
    """Список участников по сторонам: ник и Game ID."""
    t_cap, ct_cap = side_caps(t)
    finished = t.status == TournamentStatus.finished
    groups = [("T", t_cap), ("CT", ct_cap)]
    parts = []
    for side, cap in groups:
        members = [r for r in regs if r.side == side]
        lines = [f"{SIDE_SHORT[side]} ({len(members)}/{cap}):"]
        if not members:
            lines.append("   —")
        for i, r in enumerate(members, 1):
            crown = " 🏆" if finished and r.is_winner else ""
            lines.append(f"   {i}. {_nick(r)} — <code>{escape(r.game_id)}</code>{crown}")
        parts.append("\n".join(lines))
    no_side = [r for r in regs if r.side not in ("T", "CT")]
    if no_side:
        lines = [f"Без стороны ({len(no_side)}):"]
        for i, r in enumerate(no_side, 1):
            crown = " 🏆" if finished and r.is_winner else ""
            lines.append(f"   {i}. {_nick(r)} — <code>{escape(r.game_id)}</code>{crown}")
        parts.append("\n".join(lines))
    return "👥 <b>Участники</b>\n" + "\n\n".join(parts)


def _status_block(t, mine, regs) -> str:
    if t.status == TournamentStatus.running:
        if mine:
            return (
                "▶️ <b>Турнир начался!</b>\n"
                "Ожидайте в игре, пока вас пригласят в лобби."
            )
        return "▶️ <b>Турнир уже идёт.</b> Регистрация закрыта."
    if t.status == TournamentStatus.finished:
        if t.winner_side in ("T", "CT"):
            res = f"🏆 Победила сторона {SIDE_SHORT[t.winner_side]}"
        else:
            winners = [r for r in regs if r.is_winner]
            if winners:
                res = "🏆 Победители: " + ", ".join(_nick(r) for r in winners)
            else:
                res = "Победители не назначены"
        return f"🏁 <b>Турнир завершён.</b>\n{res}"
    if t.status == TournamentStatus.cancelled:
        return "❌ Турнир отменён."
    if t.registration_open:
        return "🟢 Регистрация открыта"
    return "🔒 Регистрация закрыта — ожидайте старта от администратора."


def _header(t, regs) -> str:
    t_cap, ct_cap = side_caps(t)
    n_t = sum(1 for r in regs if r.side == "T")
    n_ct = sum(1 for r in regs if r.side == "CT")
    cost = "Бесплатно" if t.registration_cost == 0 else f"{t.registration_cost} Gold"
    return (
        f"🏆 <b>{escape(t.title)}</b>\n\n{escape(t.description)}\n\n"
        f"📅 Старт: когда наберётся полный состав\n"
        f"🎮 Формат: {escape(t.format)}\n"
        f"👥 Слоты: <b>{len(regs)}/{t.max_participants}</b> "
        f"(🟠 Т {n_t}/{t_cap} · 🔵 КТ {n_ct}/{ct_cap})\n"
        f"🪙 Стоимость регистрации: {cost}\n🏅 Призы: {escape(t.prize_fund)}\n"
        f"📜 Условия: {escape(t.conditions)}\n"
        f"ℹ️ {escape(t.additional_info or '—')}"
    )


async def render_tour(tid, uid):
    """(text, keyboard) карточки турнира для конкретного игрока."""
    loaded = await _load(tid, uid)
    if not loaded:
        return "Турнир не найден.", main_back(), None, None
    t, regs, mine = loaded
    text = _header(t, regs) + "\n\n" + _status_block(t, mine, regs)
    if mine and mine.side in ("T", "CT") and t.status in (TournamentStatus.open, TournamentStatus.running):
        text += f"\nВы играете за: <b>{SIDE_SHORT[mine.side]}</b>"
    text += "\n\n" + _participants_block(t, regs)
    if len(text) > 4000:
        text = text[:3990] + "…"
    is_open = t.status == TournamentStatus.open
    kb = tournament_detail(
        tid,
        registered=bool(mine),
        can_leave=bool(mine) and is_open,
        can_register=is_open and t.registration_open and len(regs) < t.max_participants,
        can_switch=bool(mine) and is_open,
        has_shot=t.status == TournamentStatus.finished and bool(t.result_screenshot),
        back="tours_done" if t.status == TournamentStatus.finished else "tours",
    )
    return text, kb, None


async def render_pick(tid, uid, mode):
    """Экран выбора стороны (mode: 'reg' — регистрация, 'sw' — смена стороны)."""
    loaded = await _load(tid, uid)
    if not loaded:
        return "Турнир не найден.", main_back(), None, None
    t, regs, mine = loaded
    if t.status != TournamentStatus.open or (mode == "reg" and (mine or not t.registration_open)) or (mode == "sw" and not mine):
        return await render_tour(tid, uid)  # выбирать уже нечего — показываем карточку
    t_cap, ct_cap = side_caps(t)
    by_side = {"T": sum(1 for r in regs if r.side == "T"), "CT": sum(1 for r in regs if r.side == "CT")}
    title = "Выберите, за какую сторону хотите играть:" if mode == "reg" else "Выберите новую сторону:"
    text = f"🏆 <b>{escape(t.title)}</b> · {escape(t.format)}\n\n{title}\n🟠 Т — {by_side['T']}/{t_cap}\n🔵 КТ — {by_side['CT']}/{ct_cap}"
    return text, side_pick_kb(tid, mode, by_side, t_cap, ct_cap), None, None


def main_back():
    from app.keyboards import back_kb
    return back_kb()


async def _show(call: CallbackQuery, text, kb, kind, tid=None, uid=None, photo=None):
    """Отредактировать сообщение и запомнить для живых обновлений."""
    try:
        if call.message.photo:
            await call.message.edit_caption(caption=text, reply_markup=kb)
        else:
            await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            try:
                await call.message.delete()
            except Exception:
                pass
            sent = await call.bot.send_message(call.message.chat.id, text, reply_markup=kb)
            live.track(sent.chat.id, sent.message_id, kind, tid, uid)
            return
    live.track(call.message.chat.id, call.message.message_id, kind, tid, uid)


@router.message(F.text == "🏆 Турниры")
async def tournaments(message: Message):
    text, kb = await render_list()
    photo = asset("tournaments.png")
    if photo:
        sent = await message.answer_photo(photo, caption=text, reply_markup=kb)
        live.track(sent.chat.id, sent.message_id, "list", media=True)
    else:
        sent = await message.answer(text, reply_markup=kb)
        live.track(sent.chat.id, sent.message_id, "list")


@router.callback_query(F.data == "tours")
async def tours_cb(call: CallbackQuery):
    text, kb = await render_list()
    await _show(call, text, kb, "list")
    await call.answer()


@router.callback_query(F.data == "tours_done")
async def tours_done_cb(call: CallbackQuery):
    async with SessionLocal() as s:
        items = (
            await s.execute(
                select(Tournament).where(Tournament.status == TournamentStatus.finished)
                .order_by(Tournament.finished_at.desc().nullslast(), Tournament.id.desc()).limit(10)
            )
        ).scalars().all()
    text = "🏁 <b>Завершённые турниры</b>\nВыберите, чтобы посмотреть результат:" if items else "🏁 Завершённых турниров пока нет."
    live.untrack(call.message.chat.id, call.message.message_id)
    await call.message.edit_text(text, reply_markup=finished_list(items))
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("tour:"))
async def tour_detail_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        await s.commit()
    text, kb, photo = await render_tour(tid, u.id)
    await _show(call, text, kb, "detail", tid, u.id, photo=photo)
    await call.answer()


@router.callback_query(F.data == "side_full")
async def side_full_cb(call: CallbackQuery):
    await call.answer("Эта сторона уже заполнена, выберите другую.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("rp:") or c.data.startswith("reg:"))
async def register_pick_cb(call: CallbackQuery):
    """Шаг 1 регистрации: выбор стороны."""
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        await s.commit()
    if not u.game_id:
        await call.answer("Сначала укажите Game ID через /start", show_alert=True)
        return
    text, kb, photo = await render_pick(tid, u.id, "reg")
    await _show(call, text, kb, "pick_reg", tid, u.id)
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("rs:"))
async def register_cb(call: CallbackQuery):
    """Шаг 2 регистрации: регистрация на выбранную сторону."""
    _, tid, side = call.data.split(":")
    tid = int(tid)
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        if not u.game_id:
            await s.commit()
            await call.answer("Сначала укажите Game ID через /start", show_alert=True)
            return
        filled = False
        try:
            _, filled = await create_registration(s, u.id, tid, side)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            # показать актуальное состояние (например, сторона уже занята)
            text, kb, photo = await render_pick(tid, u.id, "reg")
            try:
                await _show(call, text, kb, "pick_reg", tid, u.id)
            except Exception:
                pass
            return
        uid = u.id
    msg = f"Регистрация успешна! Вы за {SIDE_SHORT[side]}."
    if filled:
        msg += " Состав набран — регистрация закрыта."
    await call.answer(msg, show_alert=True)
    text, kb, photo = await render_tour(tid, uid)
    await _show(call, text, kb, "detail", tid, uid, photo=photo)
    live.schedule_refresh(call.bot, tid)
    if filled:
        async with SessionLocal() as s:
            ids = await list_tournament_participant_ids(s, tid)
            t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
            title = escape(t.title) if t else str(tid)
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


@router.callback_query(lambda c: c.data.startswith("sp:"))
async def switch_pick_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        await s.commit()
    text, kb, photo = await render_pick(tid, u.id, "sw")
    await _show(call, text, kb, "pick_sw", tid, u.id)
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("ss:"))
async def switch_cb(call: CallbackQuery):
    _, tid, side = call.data.split(":")
    tid = int(tid)
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        try:
            await change_side(s, u.id, tid, side)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            text, kb, photo = await render_tour(tid, u.id)
            try:
                await _show(call, text, kb, "detail", tid, u.id, photo=photo)
            except Exception:
                pass
            return
        uid = u.id
    await call.answer(f"Теперь вы за {SIDE_SHORT[side]}")
    text, kb, photo = await render_tour(tid, uid)
    await _show(call, text, kb, "detail", tid, uid, photo=photo)
    live.schedule_refresh(call.bot, tid)


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
    text, kb, photo = await render_tour(tid, uid)
    await _show(call, text, kb, "detail", tid, uid, photo=photo)
    live.schedule_refresh(call.bot, tid)


@router.callback_query(lambda c: c.data.startswith("shot:"))
async def shot_cb(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
    if not t or not t.result_screenshot:
        await call.answer("Скриншота нет", show_alert=True)
        return
    await call.message.answer_photo(t.result_screenshot, caption=f"📸 Статистика матча · {escape(t.title)}")
    await call.answer()
