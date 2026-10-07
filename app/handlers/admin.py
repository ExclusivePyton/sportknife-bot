from decimal import Decimal, InvalidOperation
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from app.config import settings
from app.db import SessionLocal
from app.timeutil import parse_msk
from app.models import User, Tournament, Registration, Withdrawal, WithdrawalStatus, TournamentStatus, PromoCode
from app.services import (
    get_or_create_user, add_gold, pay_withdrawal, reject_withdrawal, apply_result,
    create_promo, list_promos, deactivate_promo,
    list_all_channels, add_required_channel, deactivate_channel,
    list_all_telegram_ids, ban_user, unban_user, list_tournament_participant_ids,
)
from app.keyboards import admin_menu, admin_tournament_actions, withdrawal_actions, promo_deactivate_kb, channel_remove_kb, users_list_kb, player_actions_kb
from app.states import AdminGoldStates, AdminFindStates, TournamentCreateStates, ResultStates, AdminPromoStates, AdminChannelStates, AdminEditUserStates, AdminBanStates, TourBroadcastStates, AdminBroadcastStates

router = Router()

def admin_only(uid): return uid in settings.admin_ids

@router.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: Message):
    if not admin_only(message.from_user.id): return
    await message.answer("⚙️ <b>Админ-панель</b>", reply_markup=admin_menu())

PAGE_SIZE = 15


async def _send_users_page(message_or_call, page: int = 0):
    async with SessionLocal() as s:
        total = (await s.execute(select(func.count(User.id)))).scalar_one()
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        users = (
            await s.execute(
                select(User).order_by(User.id.desc()).offset(page * PAGE_SIZE).limit(PAGE_SIZE)
            )
        ).scalars().all()
    text = (
        f"👥 <b>Игроки бота</b> (стр. {page+1}/{total_pages}, всего {total})\n\n"
        "Нажмите на игрока: Gold / ник / ID / бан."
    )
    kb = users_list_kb(users, page, total_pages)
    if hasattr(message_or_call, "message") and message_or_call.message:
        # CallbackQuery
        try:
            await message_or_call.message.edit_text(text, reply_markup=kb)
        except Exception:
            await message_or_call.message.answer(text, reply_markup=kb)
        await message_or_call.answer()
    else:
        await message_or_call.answer(text, reply_markup=kb)


@router.callback_query(lambda c: c.data == "admin:gold")
async def admin_gold(call: CallbackQuery, state: FSMContext):
    # устаревшая кнопка — тот же список игроков
    if not admin_only(call.from_user.id):
        return
    await state.clear()
    await _send_users_page(call, 0)


@router.callback_query(lambda c: c.data == "admin:users")
async def admin_users(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.clear()
    await _send_users_page(call, 0)


@router.callback_query(lambda c: c.data and c.data.startswith("users_page:"))
async def users_page(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    page = int(call.data.split(":")[1])
    await _send_users_page(call, page)


@router.callback_query(lambda c: c.data == "noop")
async def noop_cb(call: CallbackQuery):
    await call.answer()




@router.callback_query(lambda c: c.data and c.data.startswith("act_gold:"))
async def act_gold(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        await call.answer("Не найден", show_alert=True)
        return
    await state.update_data(tid=u.telegram_id, user_db_id=u.id)
    await state.set_state(AdminGoldStates.amount)
    await call.message.answer(
        f"🪙 Выдача Gold игроку <code>{u.game_id or u.telegram_id}</code>\nВведите количество:"
    )
    await call.answer()

@router.callback_query(lambda c: c.data == "admin:gold_tid")
async def admin_gold_tid(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.set_state(AdminGoldStates.telegram_id)
    await call.message.answer("🪙 Введите Telegram ID игрока:")
    await call.answer()


@router.callback_query(lambda c: c.data in ("admin:gold_search", "admin:user_search"))
async def admin_gold_search(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.set_state(AdminGoldStates.telegram_id)  # reuse: we'll treat as search
    await state.update_data(gold_mode="search")
    await call.message.answer("🔎 Введите Game ID (8 цифр) или часть ника:")
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("gold_pick:"))
async def gold_pick(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        await call.answer("Игрок не найден", show_alert=True)
        return
    await state.clear()
    ban_line = "🚫 ЗАБЛОКИРОВАН" if getattr(u, "is_banned", False) else "активен"
    text = (
        f"👤 <b>Игрок</b>\n"
        f"🎮 Game ID: <code>{u.game_id or '—'}</code>\n"
        f"🏷 Ник: {u.nickname or u.username or '—'}\n"
        f"🆔 TG: <code>{u.telegram_id}</code>\n"
        f"🪙 Баланс: {u.balance} Gold\n"
        f"Статус: {ban_line}\n\n"
        "Выберите действие:"
    )
    await call.message.answer(text, reply_markup=player_actions_kb(u.id, getattr(u, "is_banned", False)))
    await call.answer()


@router.message(AdminGoldStates.telegram_id)
async def ag_id(message: Message, state: FSMContext):
    d = await state.get_data()
    text = (message.text or "").strip()
    if d.get("gold_mode") == "search":
        async with SessionLocal() as s:
            q = select(User)
            if text.isdigit() and len(text) == 8:
                q = q.where(User.game_id == text)
            else:
                like = f"%{text}%"
                q = q.where(
                    (User.nickname.ilike(like))
                    | (User.username.ilike(like))
                    | (User.game_id.ilike(like))
                )
            users = (await s.execute(q.order_by(User.id.desc()).limit(20))).scalars().all()
        if not users:
            await message.answer("Никого не найдено. Попробуйте ещё раз или откройте список.")
            return
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = []
        for u in users:
            rows.append([InlineKeyboardButton(
                text=f"🎮 {u.game_id or '—'} | {u.nickname or u.username or '—'} | 🪙{u.balance}",
                callback_data=f"gold_pick:{u.id}",
            )])
        await state.clear()
        await message.answer("Найдено:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return
    try:
        tid = int(text)
    except Exception:
        await message.answer("Нужен числовой Telegram ID.")
        return
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.telegram_id == tid))).scalar_one_or_none()
    if not u:
        await message.answer("Игрок с таким Telegram ID не найден в боте.")
        return
    await state.update_data(tid=tid, user_db_id=u.id)
    await state.set_state(AdminGoldStates.amount)
    await message.answer(
        f"Игрок: 🎮 <code>{u.game_id or '—'}</code> | {u.nickname or '—'}\n"
        f"Баланс: {u.balance} Gold\n\nВведите количество Gold:"
    )


@router.message(AdminGoldStates.amount)
async def ag_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").replace(",", ".").strip())
    except Exception:
        await message.answer("Введите число.")
        return
    if amount <= 0:
        await message.answer("Сумма должна быть > 0.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(AdminGoldStates.reason)
    await message.answer("Укажите причину начисления (увидит игрок):")


@router.message(AdminGoldStates.reason)
async def ag_reason(message: Message, state: FSMContext):
    d = await state.get_data()
    reason = (message.text or "").strip() or "без указания причины"
    amount = Decimal(d["amount"])
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.telegram_id == d["tid"]))).scalar_one_or_none()
        if not u:
            await message.answer("Игрок не найден.")
            await state.clear()
            return
        from app.models import TransactionType
        await add_gold(s, u.id, amount, TransactionType.admin_credit, reason, "admin")
        await s.commit()
        tg_id = u.telegram_id
        game_id = u.game_id
    await state.clear()
    await message.answer(
        f"✅ Начислено <b>{amount}</b> Gold\n"
        f"Игрок: 🎮 <code>{game_id or '—'}</code> (TG <code>{tg_id}</code>)"
    )
    # Уведомление игроку
    try:
        await message.bot.send_message(
            tg_id,
            f"🪙 Вам начислено <b>{amount}</b> Gold\n\n"
            f"Причина: {reason}\n"
            f"Выдал: администратор",
        )
    except Exception:
        await message.answer("⚠️ Gold начислен, но сообщение игроку отправить не удалось (он не писал боту / блок).")

@router.callback_query(lambda c: c.data == "admin:withdrawals")
async def admin_withdrawals(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    async with SessionLocal() as s:
        rows = (await s.execute(select(Withdrawal).where(Withdrawal.status == WithdrawalStatus.pending).order_by(Withdrawal.created_at))).scalars().all()
        users = {}
        for w in rows:
            users[w.id] = (await s.execute(select(User).where(User.id == w.user_id))).scalar_one()
    if not rows:
        await call.message.answer("💸 Нет заявок в обработке."); await call.answer(); return
    for w in rows:
        u = users[w.id]
        text = (f"💸 <b>Заявка #{w.id}</b>\n👤 {u.nickname or '—'}\n🎮 Game ID: {u.game_id or '—'}\n"
                f"🆔 Telegram ID: {u.telegram_id}\n🪙 Сумма: {w.amount} Gold\n🔫 {w.skin_name}\n🎨 Pattern: {w.pattern}")
        await call.message.answer_photo(w.screenshot_file_id, caption=text, reply_markup=withdrawal_actions(w.id))
    await call.answer()

@router.callback_query(lambda c: c.data.startswith("wd_paid:"))
async def wd_paid(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    wid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        try:
            await pay_withdrawal(s, wid, call.from_user.id); await s.commit()
        except Exception as e:
            await s.rollback(); await call.answer(str(e), show_alert=True); return
    await call.message.edit_caption((call.message.caption or "") + "\n\n🟢 Выплачено")
    await call.answer("Выплата подтверждена.")

@router.callback_query(lambda c: c.data.startswith("wd_reject:"))
async def wd_reject(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    wid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        try:
            await reject_withdrawal(s, wid, call.from_user.id); await s.commit()
        except Exception as e:
            await s.rollback(); await call.answer(str(e), show_alert=True); return
    await call.message.edit_caption((call.message.caption or "") + "\n\n🔴 Отклонено")
    await call.answer("Заявка отклонена.")

@router.callback_query(lambda c: c.data == "admin:create_tour")
async def create_tour_start(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.set_state(TournamentCreateStates.title)
    await call.message.answer(
        "🏆 Создание турнира\n\n"
        "Введите <b>название</b> турнира:"
    )
    await call.answer()


@router.message(TournamentCreateStates.title)
async def ct_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Введите название:")
        return
    await state.update_data(title=title)
    await state.set_state(TournamentCreateStates.description)
    await message.answer("Введите <b>описание</b> турнира:")


@router.message(TournamentCreateStates.description)
async def ct_desc(message: Message, state: FSMContext):
    desc = (message.text or "").strip()
    if not desc:
        await message.answer("Описание не может быть пустым. Введите описание:")
        return
    await state.update_data(description=desc)
    await state.set_state(TournamentCreateStates.format)
    from app.keyboards import format_choice_kb
    await message.answer(
        "Старт турнира — <b>когда наберётся полный состав</b>.\n\n"
        "Выберите <b>формат</b> (в скобках число слотов):",
        reply_markup=format_choice_kb(),
    )


@router.message(TournamentCreateStates.start_at)
async def ct_date(message: Message, state: FSMContext):
    try:
        dt = parse_msk((message.text or "").strip())
    except Exception:
        await message.answer(
            "Неверный формат. Пример: <code>15.10.2026 18:30</code>\n"
            "(время <b>московское</b>, МСК)"
        )
        return
    await state.update_data(start_at=dt.isoformat())
    await state.set_state(TournamentCreateStates.format)
    from app.keyboards import format_choice_kb
    await message.answer(
        "Выберите <b>формат</b> турнира:\n"
        "В скобках — число слотов (1 слот = 1 человек).\n"
        "Пример: <code>3v3</code> → 6 слотов, <code>1v2</code> → 3 слота.",
        reply_markup=format_choice_kb(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("fmt:"))
async def ct_format_cb(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    current = await state.get_state()
    if current != TournamentCreateStates.format.state:
        await call.answer("Сначала начните создание турнира", show_alert=True)
        return
    fmt = call.data.split(":", 1)[1]
    from app.keyboards import slots_for_format
    try:
        slots = slots_for_format(fmt)
    except Exception:
        await call.answer("Неверный формат", show_alert=True)
        return
    await state.update_data(format=fmt, max_participants=slots)
    await state.set_state(TournamentCreateStates.cost)
    await call.message.edit_text(
        f"✅ Формат: <b>{fmt}</b>\n"
        f"👥 Слотов (участников): <b>{slots}</b>\n\n"
        "Введите стоимость регистрации в Gold (<code>0</code> = бесплатно):"
    )
    await call.answer()


@router.message(TournamentCreateStates.format)
async def ct_format_text(message: Message, state: FSMContext):
    from app.keyboards import format_choice_kb
    await message.answer(
        "Выберите формат <b>кнопкой</b> ниже:",
        reply_markup=format_choice_kb(),
    )


@router.message(TournamentCreateStates.max_participants)
async def ct_max_skip(message: Message, state: FSMContext):
    # Слоты теперь из формата — если старое состояние, просим формат кнопками
    from app.keyboards import format_choice_kb
    await state.set_state(TournamentCreateStates.format)
    await message.answer(
        "Слоты задаются форматом. Выберите формат кнопкой:",
        reply_markup=format_choice_kb(),
    )


@router.message(TournamentCreateStates.cost)
async def ct_cost(message: Message, state: FSMContext):
    try:
        n = Decimal((message.text or "").replace(",", ".").strip())
    except Exception:
        await message.answer("Введите число.")
        return
    if n < 0:
        await message.answer("Не может быть отрицательной.")
        return
    await state.update_data(cost=str(n))
    await state.set_state(TournamentCreateStates.prize_fund)
    await message.answer("Опишите <b>призовой фонд</b>:")


@router.message(TournamentCreateStates.prize_fund)
async def ct_prize(message: Message, state: FSMContext):
    prize = (message.text or "").strip()
    if not prize:
        await message.answer("Призовой фонд не может быть пустым.")
        return
    await state.update_data(prize=prize)
    await state.set_state(TournamentCreateStates.conditions)
    await message.answer("Введите <b>условия</b> турнира:")


@router.message(TournamentCreateStates.conditions)
async def ct_conditions(message: Message, state: FSMContext):
    cond = (message.text or "").strip()
    if not cond:
        await message.answer("Условия не могут быть пустыми.")
        return
    await state.update_data(conditions=cond)
    await state.set_state(TournamentCreateStates.additional_info)
    await message.answer("Дополнительная информация (или отправьте <code>—</code>):")


@router.message(TournamentCreateStates.additional_info)
async def ct_finish(message: Message, state: FSMContext):
    d = await state.get_data()
    extra = (message.text or "").strip()
    async with SessionLocal() as db:
        t = Tournament(
            title=d["title"],
            description=d["description"],
            start_at=__import__("app.timeutil", fromlist=["now_msk"]).now_msk(),
            format=d["format"],
            max_participants=d["max_participants"],
            registration_cost=Decimal(d["cost"]),
            prize_fund=d["prize"],
            conditions=d["conditions"],
            additional_info=None if extra in ("—", "-", "–") else extra,
            status=TournamentStatus.open,
            registration_open=True,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        tid = t.id
        title = t.title
        fmt = t.format
        slots = t.max_participants
        cost = t.registration_cost
        from app.timeutil import format_msk
        start_str = format_msk(t.start_at)
        ids = await list_all_telegram_ids(db)
    await state.clear()
    await message.answer(f"✅ Турнир создан: <b>#{tid}</b> — {title}")

    # Рассылка всем пользователям бота
    cost_txt = "бесплатно" if cost == 0 else f"{cost} Gold"
    announce = (
        f"🏆 <b>Новый турнир!</b>\n\n"
        f"<b>{title}</b>\n"
        f"📅 {start_str} (МСК)\n"
        f"🎮 Формат: {fmt} | Слотов: {slots}\n"
        f"🪙 Регистрация: {cost_txt}\n\n"
        f"Откройте «🏆 Турниры» в боте, чтобы записаться."
    )
    ok = fail = 0
    import asyncio
    for tg_id in ids:
        try:
            await message.bot.send_message(tg_id, announce)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await message.answer(f"📣 Рассылка: доставлено {ok}, не доставлено {fail}.")

@router.callback_query(lambda c: c.data == "admin:tours")
async def admin_tours(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    async with SessionLocal() as s: tours=(await s.execute(select(Tournament).order_by(Tournament.start_at.desc()).limit(30))).scalars().all()
    for t in tours: await call.message.answer(f"#{t.id} 🏆 {t.title}\nСтатус: {t.status.value}", reply_markup=admin_tournament_actions(t.id))
    await call.answer()

async def change_status(call, status):

    if not admin_only(call.from_user.id): return
    tid=int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t=(await s.execute(select(Tournament).where(Tournament.id==tid).with_for_update())).scalar_one()
        t.status=status; await s.commit()
    await call.answer(f"Статус: {status.value}")


@router.callback_query(lambda c: c.data.startswith("adm_tour_open:"))
async def tour_open(call: CallbackQuery):
    await change_status(call, TournamentStatus.open)
    tid=int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t=(await s.execute(select(Tournament).where(Tournament.id==tid).with_for_update())).scalar_one()
        t.registration_open=True
        await s.commit()

@router.callback_query(lambda c: c.data.startswith("adm_tour_close:"))
async def tour_close(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    tid=int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t=(await s.execute(select(Tournament).where(Tournament.id==tid).with_for_update())).scalar_one()
        t.registration_open=False
        await s.commit()
    await call.answer("Регистрация закрыта.")

@router.callback_query(lambda c: c.data.startswith("adm_tour_run:"))
async def tour_run(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid).with_for_update())).scalar_one()
        t.status = TournamentStatus.running
        t.registration_open = False
        title = t.title
        await s.commit()
        ids = await list_all_telegram_ids(s)
    await call.answer("Турнир запущен")
    import asyncio
    text = (
        f"▶️ <b>Турнир начался!</b>\n\n"
        f"🏆 {title}\n"
        f"Регистрация закрыта. Удачи участникам!"
    )
    for tg_id in ids:
        try:
            await call.bot.send_message(tg_id, text)
        except Exception:
            pass
        await asyncio.sleep(0.05)


@router.callback_query(lambda c: c.data.startswith("adm_tour_finish:"))
async def tour_finish(call: CallbackQuery): await change_status(call, TournamentStatus.finished)

@router.callback_query(lambda c: c.data.startswith("adm_tour_cancel:"))
async def tour_cancel(call: CallbackQuery): await change_status(call, TournamentStatus.cancelled)

@router.callback_query(lambda c: c.data.startswith("adm_tour_part:"))
async def tour_participants(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    tid=int(call.data.split(":")[1])
    async with SessionLocal() as s:
        rows=(await s.execute(
            select(Registration, User).join(User, User.id==Registration.user_id)
            .where(Registration.tournament_id==tid).order_by(Registration.created_at)
        )).all()
    if not rows:
        await call.message.answer("👥 Участников пока нет.")
    else:
        text = "👥 <b>Участники</b>\n\n"
        for i, (r, u) in enumerate(rows, 1):
            text += f"{i}. {u.nickname or '—'} | Game ID: {r.game_id} | TG: {u.telegram_id}\n"
        await call.message.answer(text)
    await call.answer()

@router.callback_query(lambda c: c.data.startswith("adm_results:"))
async def result_start(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id): return
    tid=int(call.data.split(":")[1])
    await state.update_data(tournament_id=tid)
    await state.set_state(ResultStates.place)
    await call.message.answer("🏅 Введите место (1, 2 или 3):")
    await call.answer()

@router.message(ResultStates.place)
async def result_place(m: Message, state: FSMContext):
    try: place=int(m.text)
    except: await m.answer("Введите 1, 2 или 3."); return
    if place not in (1,2,3): await m.answer("Допустимы только 1, 2 или 3."); return
    await state.update_data(place=place); await state.set_state(ResultStates.telegram_id)
    await m.answer("Введите Telegram ID игрока:")

@router.message(ResultStates.telegram_id)
async def result_user(m: Message, state: FSMContext):
    try: tid=int(m.text)
    except: await m.answer("Нужен числовой Telegram ID."); return
    async with SessionLocal() as s:
        u=(await s.execute(select(User).where(User.telegram_id==tid))).scalar_one_or_none()
    if not u: await m.answer("Игрок не найден."); return
    await state.update_data(user_id=u.id, tg_id=tid); await state.set_state(ResultStates.prize)
    await m.answer("Приз в Gold (0 если без награды):")

@router.message(ResultStates.prize)
async def result_prize(m: Message, state: FSMContext):
    try: prize=Decimal(m.text.replace(",", "."))
    except: await m.answer("Введите число."); return
    if prize < 0: await m.answer("Приз не может быть отрицательным."); return
    d=await state.get_data()
    async with SessionLocal() as s:
        try:
            await apply_result(s, d["tournament_id"], d["user_id"], d["place"], prize)
            await s.commit()
        except Exception as e:
            await s.rollback(); await m.answer(f"❌ Не удалось сохранить результат: {e}"); return
    await state.clear()
    await m.answer(f"✅ {d['place']} место сохранено. Приз: {prize} Gold.")

@router.callback_query(lambda c: c.data == "admin:participants")
async def all_participants(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    async with SessionLocal() as s:
        count=(await s.execute(select(func.count(Registration.id)))).scalar_one()
    await call.message.answer(f"👥 Всего регистраций: {count}")
    await call.answer()

@router.callback_query(lambda c: c.data == "admin:stats")
async def admin_stats(call: CallbackQuery):
    if not admin_only(call.from_user.id): return
    async with SessionLocal() as s:
        users=(await s.execute(select(func.count(User.id)))).scalar_one()
        tours=(await s.execute(select(func.count(Tournament.id)))).scalar_one()
        wds=(await s.execute(select(func.count(Withdrawal.id)).where(Withdrawal.status==WithdrawalStatus.pending))).scalar_one()
    await call.message.answer(f"📊 <b>Общая статистика</b>\n\n👤 Пользователей: {users}\n🏆 Турниров: {tours}\n💸 Заявок в обработке: {wds}")
    await call.answer()

@router.callback_query(lambda c: c.data == "admin:find")
async def admin_find(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id): return
    await state.set_state(AdminFindStates.telegram_id); await call.message.answer("Введите Telegram ID:"); await call.answer()

@router.message(AdminFindStates.telegram_id)
async def admin_find_do(message: Message, state: FSMContext):
    try:
        tid = int((message.text or "").strip())
    except Exception:
        await message.answer("Нужен числовой ID.")
        return
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.telegram_id == tid))).scalar_one_or_none()
    await state.clear()
    if not u:
        await message.answer("Игрок не найден.")
        return
    await message.answer(
        f"👤 {u.nickname or '—'}\n🎮 {u.game_id or '—'}\n🆔 {u.telegram_id}\n"
        f"🪙 {u.balance} Gold\n🔒 {u.reserved_balance} Gold"
    )


# ---------- Промокоды ----------

@router.callback_query(lambda c: c.data == "admin:promo_create")
async def admin_promo_create(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.set_state(AdminPromoStates.code)
    await call.message.answer(
        "🎁 Создание промокода\n\n"
        "Введите код (латиница/цифры, без пробелов).\n"
        "Пример: WELCOME100"
    )
    await call.answer()


@router.message(AdminPromoStates.code)
async def admin_promo_code(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    if len(code) < 3 or " " in code:
        await message.answer("Код минимум 3 символа, без пробелов.")
        return
    await state.update_data(code=code)
    await state.set_state(AdminPromoStates.gold)
    await message.answer("Сколько Gold выдавать за этот промокод?")


@router.message(AdminPromoStates.gold)
async def admin_promo_gold(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.replace(",", "."))
    except Exception:
        await message.answer("Введите число.")
        return
    if amount <= 0:
        await message.answer("Сумма должна быть > 0.")
        return
    await state.update_data(gold=str(amount))
    await state.set_state(AdminPromoStates.max_uses)
    await message.answer(
        "Сколько раз можно использовать промокод?\n"
        "Введите число. 0 = безлимит."
    )


@router.message(AdminPromoStates.max_uses)
async def admin_promo_max_uses(message: Message, state: FSMContext):
    try:
        n = int(message.text.strip())
    except Exception:
        await message.answer("Введите целое число.")
        return
    if n < 0:
        await message.answer("Не может быть отрицательным.")
        return
    await state.update_data(max_uses=n)
    await state.set_state(AdminPromoStates.note)
    await message.answer("Комментарий к промокоду (или отправьте —):")


@router.message(AdminPromoStates.note)
async def admin_promo_finish(message: Message, state: FSMContext):
    d = await state.get_data()
    note = None if (message.text or "").strip() == "—" else (message.text or "").strip()
    async with SessionLocal() as s:
        try:
            promo = await create_promo(
                s,
                code=d["code"],
                gold_amount=Decimal(d["gold"]),
                max_uses=int(d["max_uses"]),
                created_by=message.from_user.id,
                note=note,
            )
            await s.commit()
        except Exception as e:
            await s.rollback()
            await message.answer(f"❌ Не удалось создать: {e}")
            await state.clear()
            return
    await state.clear()
    limit_text = "безлимит" if promo.max_uses == 0 else str(promo.max_uses)
    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"Код: <b>{promo.code}</b>\n"
        f"Gold: <b>{promo.gold_amount}</b>\n"
        f"Лимит использований: <b>{limit_text}</b>\n"
        f"ID: #{promo.id}"
    )


@router.callback_query(lambda c: c.data == "admin:promo_list")
async def admin_promo_list(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return
    async with SessionLocal() as s:
        promos = await list_promos(s, limit=40)
    if not promos:
        await call.message.answer("📋 Промокодов пока нет.")
        await call.answer()
        return
    for p in promos:
        limit_text = "∞" if p.max_uses == 0 else str(p.max_uses)
        status = "🟢 активен" if p.is_active else "🔴 выключен"
        text = (
            f"🎁 <b>{p.code}</b> #{p.id}\n"
            f"🪙 {p.gold_amount} Gold\n"
            f"Использовано: {p.used_count} / {limit_text}\n"
            f"Статус: {status}\n"
            f"Заметка: {p.note or '—'}"
        )
        kb = promo_deactivate_kb(p.id) if p.is_active else None
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("promo_off:"))
async def admin_promo_off(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return
    pid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        try:
            promo = await deactivate_promo(s, pid)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            return
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer(f"Промокод {promo.code} отключён.")


# ---------- Обязательные каналы ----------

@router.callback_query(lambda c: c.data == "admin:channels")
async def admin_channels(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return
    async with SessionLocal() as s:
        channels = await list_all_channels(s)
    await call.message.answer(
        "📢 <b>Обязательные каналы</b>\n\n"
        "Пользователи должны быть подписаны на все <b>активные</b> каналы.\n"
        "Бот должен быть <b>администратором</b> каждого канала (чтобы проверять подписку).\n\n"
        "Чтобы добавить канал — нажмите кнопку ниже и перешлите любое сообщение из канала "
        "или отправьте @username канала."
    )
    if not channels:
        await call.message.answer("Список пуст.")
    else:
        for ch in channels:
            status = "🟢 активен" if ch.is_active else "🔴 выключен"
            uname = f"@{ch.username}" if ch.username else "—"
            text = (
                f"#{ch.id} {ch.title or '—'}\n"
                f"Username: {uname}\n"
                f"chat_id: <code>{ch.chat_id}</code>\n"
                f"Статус: {status}"
            )
            kb = channel_remove_kb(ch.id) if ch.is_active else None
            await call.message.answer(text, reply_markup=kb)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await call.message.answer(
        "Действия:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin:channel_add")],
        ]),
    )
    await call.answer()


@router.callback_query(lambda c: c.data == "admin:channel_add")
async def admin_channel_add(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.set_state(AdminChannelStates.waiting)
    await call.message.answer(
        "Пришлите:\n"
        "• пересланное сообщение из канала, или\n"
        "• @username канала (публичный), или\n"
        "• числовой chat_id канала (например -100123...)\n\n"
        "Бот должен быть админом этого канала."
    )
    await call.answer()


@router.message(AdminChannelStates.waiting)
async def admin_channel_save(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return
    chat_id = None
    username = None
    title = ""

    if message.forward_from_chat:
        chat = message.forward_from_chat
        chat_id = chat.id
        username = chat.username
        title = chat.title or ""
    elif message.text:
        text_in = message.text.strip()
        if text_in.startswith("@"):
            username = text_in.lstrip("@")
            try:
                chat = await message.bot.get_chat(f"@{username}")
                chat_id = chat.id
                title = chat.title or username
                username = chat.username or username
            except Exception as e:
                await message.answer(f"❌ Не удалось найти канал @{username}: {e}")
                return
        elif text_in.lstrip("-").isdigit():
            chat_id = int(text_in)
            try:
                chat = await message.bot.get_chat(chat_id)
                username = chat.username
                title = chat.title or str(chat_id)
            except Exception as e:
                await message.answer(
                    f"❌ Не удалось получить канал {chat_id}: {e}. "
                    "Убедитесь, что бот добавлен в канал как администратор."
                )
                return
        else:
            await message.answer("Пришлите @username, chat_id или пересланное сообщение из канала.")
            return
    else:
        await message.answer("Пришлите @username, chat_id или пересланное сообщение из канала.")
        return

    try:
        me = await message.bot.get_me()
        member = await message.bot.get_chat_member(chat_id, me.id)
        from aiogram.enums import ChatMemberStatus
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.answer(
                "❌ Бот не администратор этого канала. "
                "Добавьте бота в канал как администратора "
                "(права: управление пользователями / просмотр участников) и попробуйте снова."
            )
            return
    except Exception as e:
        await message.answer(
            f"❌ Не удалось проверить канал. Добавьте бота как администратора. Ошибка: {e}"
        )
        return

    async with SessionLocal() as s:
        try:
            ch = await add_required_channel(s, chat_id, username, title)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await message.answer(f"❌ Ошибка: {e}")
            await state.clear()
            return
    await state.clear()
    await message.answer(
        f"✅ Канал успешно добавлен!\n\n<b>{ch.title}</b>\n"
        f"chat_id: <code>{ch.chat_id}</code>\nusername: @{ch.username or '—'}\n\n"
        "Теперь при входе в бота будет проверка подписки."
    )



@router.callback_query(lambda c: c.data.startswith("ch_off:"))
async def admin_channel_off(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return
    cid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        try:
            ch = await deactivate_channel(s, cid)
            await s.commit()
        except Exception as e:
            await s.rollback()
            await call.answer(str(e), show_alert=True)
            return
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer(f"Канал {ch.title or ch.chat_id} убран из обязательных.")


# ---------- Правка профиля игрока ----------

@router.callback_query(lambda c: c.data == "admin:edit_user")
async def admin_edit_user(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.clear()
    await _send_users_page(call, 0)



@router.message(AdminEditUserStates.search)
async def admin_edit_search(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return
    text = (message.text or "").strip()
    async with SessionLocal() as s:
        users = []
        if text.isdigit():
            tid = int(text)
            q = select(User).where((User.game_id == text) | (User.telegram_id == tid)).limit(20)
            users = (await s.execute(q)).scalars().all()
        if not users:
            like = f"%{text}%"
            users = (
                await s.execute(
                    select(User).where(
                        (User.nickname.ilike(like))
                        | (User.username.ilike(like))
                        | (User.game_id.ilike(like))
                    ).order_by(User.id.desc()).limit(20)
                )
            ).scalars().all()
    if not users:
        await message.answer("Игрок не найден. Попробуйте ещё раз:")
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    for u in users:
        rows.append([InlineKeyboardButton(
            text=f"🎮 {u.game_id or '—'} | {u.nickname or u.username or '—'} | {u.telegram_id}",
            callback_data=f"edit_user:{u.id}",
        )])
    await state.clear()
    await message.answer("Выберите игрока:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(lambda c: c.data and c.data.startswith("edit_user:"))
async def edit_user_pick(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        await call.answer("Не найден", show_alert=True)
        return
    await state.update_data(edit_user_id=uid)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Изменить Game ID", callback_data="edit_field:game_id")],
        [InlineKeyboardButton(text="🏷 Изменить NickName", callback_data="edit_field:nickname")],
        ([InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"unban:{u.id}")] if getattr(u, "is_banned", False) else [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"ban:{u.id}")]),
    ])
    await call.message.answer(
        f"Игрок: 🎮 <code>{u.game_id or '—'}</code>\n"
        f"Ник: {u.nickname or '—'}\n"
        f"TG: <code>{u.telegram_id}</code>\n\n"
        "Что изменить?",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit_field:"))
async def edit_field_pick(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    parts = call.data.split(":")
    field = parts[1]
    if len(parts) >= 3:
        await state.update_data(edit_user_id=int(parts[2]), edit_field=field)
    else:
        await state.update_data(edit_field=field)
    await state.set_state(AdminEditUserStates.value)
    if field == "game_id":
        await call.message.answer("Введите новый Game ID (ровно 8 цифр):")
    else:
        await call.message.answer("Введите новый NickName:")
    await call.answer()


@router.message(AdminEditUserStates.value)
async def edit_user_value(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return
    d = await state.get_data()
    uid = d.get("edit_user_id")
    field = d.get("edit_field")
    value = (message.text or "").strip()
    if not uid or not field:
        await state.clear()
        await message.answer("Сессия сброшена. Начните снова из админ-панели.")
        return
    if field == "game_id":
        if not (value.isdigit() and len(value) == 8):
            await message.answer("Game ID должен быть ровно 8 цифр. Попробуйте ещё раз:")
            return
    elif field == "nickname":
        if not value or len(value) > 64:
            await message.answer("Ник от 1 до 64 символов. Попробуйте ещё раз:")
            return
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == uid).with_for_update())).scalar_one_or_none()
        if not u:
            await message.answer("Игрок не найден.")
            await state.clear()
            return
        if field == "game_id":
            u.game_id = value
        else:
            u.nickname = value
        tg_id = u.telegram_id
        await s.commit()
    await state.clear()
    await message.answer(f"✅ Обновлено: <b>{field}</b> = <code>{value}</code>")
    try:
        label = "Game ID" if field == "game_id" else "NickName"
        await message.bot.send_message(
            tg_id,
            f"✏️ Администратор изменил ваш {label}:\n<code>{value}</code>",
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("ban:"))
async def ban_start(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(ban_user_id=uid)
    await state.set_state(AdminBanStates.reason)
    await call.message.answer("Введите причину блокировки (увидит игрок):")
    await call.answer()


@router.message(AdminBanStates.reason)
async def ban_reason(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой:")
        return
    d = await state.get_data()
    uid = d.get("ban_user_id")
    async with SessionLocal() as s:
        u = await ban_user(s, uid, reason)
        await s.commit()
        tg_id = u.telegram_id
    await state.clear()
    await message.answer(f"🚫 Игрок заблокирован. Причина: {reason}")
    try:
        from app.keyboards import SUPPORT_USERNAME
        await message.bot.send_message(
            tg_id,
            f"🚫 Вы заблокированы в боте.\n\nПричина: {reason}\n\nДля обжалования пишите в поддержку: @{SUPPORT_USERNAME}",
        )
    except Exception:
        await message.answer("⚠️ Сообщение игроку отправить не удалось.")


@router.callback_query(lambda c: c.data and c.data.startswith("unban:"))
async def unban_cb(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await unban_user(s, uid)
        await s.commit()
        tg_id = u.telegram_id
    await call.answer("Разблокирован")
    await call.message.answer(f"✅ Игрок {u.game_id or tg_id} разблокирован.")
    try:
        await call.bot.send_message(tg_id, "✅ Вы снова разблокированы в боте.")
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("adm_tour_bc:"))
async def tour_bc_start(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    tid = int(call.data.split(":")[1])
    await state.update_data(bc_tour_id=tid)
    await state.set_state(TourBroadcastStates.text)
    await call.message.answer("📣 Введите текст рассылки для участников этого турнира:")
    await call.answer()


@router.message(TourBroadcastStates.text)
async def tour_bc_send(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return
    body_text = (message.text or "").strip()
    if not body_text:
        await message.answer("Текст пустой. Введите сообщение:")
        return
    d = await state.get_data()
    tid = d.get("bc_tour_id")
    await state.clear()
    async with SessionLocal() as s:
        ids = await list_tournament_participant_ids(s, tid)
    if not ids:
        await message.answer("Участников нет.")
        return
    import asyncio
    ok = fail = 0
    body = f"📣 <b>Сообщение по турниру #{tid}</b>\n\n{body_text}"
    for tg_id in ids:
        try:
            await message.bot.send_message(tg_id, body)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await message.answer(f"Рассылка участникам: доставлено {ok}, не доставлено {fail}.")


@router.callback_query(lambda c: c.data == "admin:broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        return
    await state.set_state(AdminBroadcastStates.text)
    await call.message.answer(
        "📣 Введите текст рассылки <b>всем</b> пользователям бота:\n"
        "Отмена: /cancel"
    )
    await call.answer()


@router.message(AdminBroadcastStates.text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return
    body_text = (message.text or "").strip()
    if not body_text:
        await message.answer("Текст пустой:")
        return
    await state.clear()
    async with SessionLocal() as s:
        ids = await list_all_telegram_ids(s)
    import asyncio
    ok = fail = 0
    body = f"📣 <b>Сообщение от администрации</b>\n\n{body_text}"
    for tg_id in ids:
        try:
            await message.bot.send_message(tg_id, body)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await message.answer(f"Рассылка завершена: доставлено {ok}, ошибок {fail}.")
