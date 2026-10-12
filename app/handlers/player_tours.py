"""Создание турниров игроками (бесплатно / на Gold через гаранта)."""
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Tournament, TournamentStatus, User, Registration
from app.services import get_or_create_user, list_all_telegram_ids
from app.states import PlayerCreateTourStates, PlayerResultStates
from app.keyboards import (
    main_menu, format_choice_kb, slots_for_format, player_mode_kb,
    player_confirm_kb, leader_actions_kb, admin_guarantor_kb, admin_player_result_kb,
    SUPPORT_USERNAME,
)
from app.timeutil import now_msk
from app import live
import asyncio

router = Router()


def is_admin(uid: int) -> bool:
    return uid in settings.admin_ids


@router.message(F.text == "➕ Создать турнир")
async def pt_start(message: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        await s.commit()
    if not u.game_id:
        await message.answer("Сначала укажите Game ID через /start.")
        return
    await state.set_state(PlayerCreateTourStates.title)
    await message.answer(
        "➕ <b>Создание своего турнира</b>\n\n"
        "Вы станете <b>лидером</b> лобби: пригласите игроков и запустите матч.\n\n"
        "Введите <b>название</b> турнира:\n"
        "Отмена: /cancel"
    )


@router.message(PlayerCreateTourStates.title)
async def pt_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("Слишком короткое название:")
        return
    if len(title) > 80:
        await message.answer("Максимум 80 символов:")
        return
    await state.update_data(title=title)
    await state.set_state(PlayerCreateTourStates.format)
    await message.answer("Выберите <b>формат</b>:", reply_markup=format_choice_kb())


@router.callback_query(PlayerCreateTourStates.format, F.data.startswith("fmt:"))
async def pt_format(call: CallbackQuery, state: FSMContext):
    fmt = call.data.split(":", 1)[1]
    try:
        slots = slots_for_format(fmt)
    except Exception:
        await call.answer("Неверный формат", show_alert=True)
        return
    await state.update_data(format=fmt, slots=slots)
    await state.set_state(PlayerCreateTourStates.mode)
    await call.message.answer(
        f"Формат <b>{fmt}</b> · слотов: <b>{slots}</b>\n\n"
        "Турнир на <b>Gold</b> или просто так?\n\n"
        "🪙 <b>На Gold</b> — вы передаёте приз гаранту (@{0}), "
        "после матча гарант выдаёт Gold победителям по скриншоту.\n"
        "🆓 <b>Просто так</b> — играете без Gold, в конце сдаёте результат на обработку.".format(SUPPORT_USERNAME),
        reply_markup=player_mode_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "pt_cancel")
async def pt_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Создание отменено.", reply_markup=main_menu(is_admin(call.from_user.id)))
    await call.answer()


@router.callback_query(PlayerCreateTourStates.mode, F.data.startswith("pt_mode:"))
async def pt_mode(call: CallbackQuery, state: FSMContext):
    mode = call.data.split(":")[1]
    await state.update_data(gold_enabled=(mode == "gold"))
    if mode == "gold":
        await state.set_state(PlayerCreateTourStates.prize)
        await call.message.answer(
            "🪙 Сколько <b>Gold</b> будет в призовом фонде?\n"
            "(Эту сумму вы передадите гаранту перед стартом записи.)\n"
            "Введите число:"
        )
    else:
        await state.update_data(prize=Decimal("0"))
        await state.set_state(PlayerCreateTourStates.description)
        await call.message.answer(
            "Краткое описание / условия (или «—»):"
        )
    await call.answer()


@router.message(PlayerCreateTourStates.prize)
async def pt_prize(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").replace(",", ".").strip())
        if amount <= 0:
            raise InvalidOperation
    except Exception:
        await message.answer("Введите положительное число:")
        return
    await state.update_data(prize=amount)
    await state.set_state(PlayerCreateTourStates.description)
    await message.answer("Краткое описание / условия (или «—»):")


@router.message(PlayerCreateTourStates.description)
async def pt_desc(message: Message, state: FSMContext):
    desc = (message.text or "").strip()
    if desc in ("—", "-", "–"):
        desc = "Турнир от игрока"
    await state.update_data(description=desc)
    d = await state.get_data()
    gold = d.get("gold_enabled")
    prize = d.get("prize", 0)
    text = (
        f"Проверьте:\n\n"
        f"🏆 <b>{escape(d['title'])}</b>\n"
        f"🎮 {d['format']} · {d['slots']} слотов\n"
        f"{'🪙 На Gold · фонд: ' + str(prize) if gold else '🆓 Бесплатно'}\n"
        f"📝 {escape(desc)}\n\n"
        f"Вы — лидер лобби."
    )
    await state.set_state(PlayerCreateTourStates.confirm)
    await message.answer(text, reply_markup=player_confirm_kb())


@router.callback_query(PlayerCreateTourStates.confirm, F.data == "pt_confirm")
async def pt_confirm(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    gold = bool(d.get("gold_enabled"))
    prize = Decimal(d.get("prize") or 0)
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        t = Tournament(
            title=d["title"],
            description=d.get("description") or "Турнир от игрока",
            start_at=now_msk(),
            format=d["format"],
            max_participants=int(d["slots"]),
            registration_cost=Decimal("0"),
            prize_fund=f"{prize} Gold (гарант)" if gold else "Без призового фонда",
            conditions="Турнир создан игроком. Лидер приглашает участников и запускает матч.",
            additional_info=None,
            status=TournamentStatus.open,
            registration_open=not gold,  # на gold — после подтверждения гаранта
            creator_id=u.id,
            is_player_created=True,
            gold_enabled=gold,
            guarantor_status="awaiting_gold" if gold else "none",
            prize_pool_gold=prize if gold else Decimal("0"),
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id
        title = t.title
        fmt = t.format
        slots = t.max_participants
        creator_tg = u.telegram_id
        nick = u.nickname or u.username or str(u.telegram_id)
        game_id = u.game_id or "—"
    await state.clear()

    if gold:
        await call.message.answer(
            f"✅ Турнир <b>#{tid} {escape(title)}</b> создан.\n\n"
            f"🪙 Режим <b>на Gold</b>. Запись откроется после того, как гарант подтвердит получение фонда.\n\n"
            f"1) Напишите гаранту @{SUPPORT_USERNAME}\n"
            f"2) Передайте <b>{prize}</b> Gold\n"
            f"3) Дождитесь подтверждения в боте\n"
            f"4) Соберите игроков и нажмите «Начать турнир»\n"
            f"5) После матча — «Сдать результат» (скрин статистики)",
            reply_markup=main_menu(is_admin(call.from_user.id)),
        )
        # уведомить админов
        note = (
            f"🪙 <b>Новый турнир на Gold #{tid}</b>\n"
            f"🏆 {escape(title)} · {fmt} · {slots} слотов\n"
            f"💰 Фонд: <b>{prize}</b> Gold\n"
            f"👤 Лидер: {escape(nick)} · 🎮 <code>{escape(str(game_id))}</code>\n"
            f"TG: <code>{creator_tg}</code> · @{escape(call.from_user.username or '—')}\n\n"
            f"Подтвердите получение Gold, когда лидер передаст фонд."
        )
        for admin_id in settings.admin_ids:
            try:
                await call.bot.send_message(admin_id, note, reply_markup=admin_guarantor_kb(tid))
            except Exception:
                pass
    else:
        await call.message.answer(
            f"✅ Турнир <b>#{tid} {escape(title)}</b> создан.\n"
            f"Запись открыта. Соберите игроков, затем «Начать турнир».\n"
            f"После матча нажмите «Сдать результат».",
            reply_markup=main_menu(is_admin(call.from_user.id)),
        )
        # рассылка
        announce = (
            f"🏆 <b>Новый турнир от игрока!</b>\n\n"
            f"<b>{escape(title)}</b>\n"
            f"🎮 {fmt} · слотов: {slots}\n"
            f"🆓 Бесплатно\n"
            f"Лидер: {escape(nick)}\n\n"
            f"Откройте «🏆 Турниры» в боте."
        )
        async with SessionLocal() as s:
            ids = await list_all_telegram_ids(s)
        for tg_id in ids:
            try:
                await call.bot.send_message(tg_id, announce)
            except Exception:
                pass
            await asyncio.sleep(0.04)

    live.schedule_refresh(call.bot, None)
    await call.answer()


# ----- leader panel -----
@router.callback_query(F.data.startswith("pt_lead:"))
async def pt_lead_panel(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
        if not t or not t.is_player_created or t.creator_id != u.id:
            await call.answer("Вы не лидер этого турнира", show_alert=True)
            return
        count = (await s.execute(
            select(Registration).where(Registration.tournament_id == tid)
        )).scalars().all()
        n = len(count)

    gold_waiting = t.gold_enabled and t.guarantor_status == "awaiting_gold"
    can_start = (
        t.status == TournamentStatus.open
        and not gold_waiting
        and n >= 2  # минимум двое
        and (n >= t.max_participants or True)  # можно стартовать и не полным? user said invite all - allow start when at least 2
    )
    # better: can start when registration closed or full or leader force with >=2
    can_start = t.status == TournamentStatus.open and not gold_waiting and n >= 2
    can_submit = t.status == TournamentStatus.running and t.guarantor_status not in ("awaiting_result", "done")

    text = (
        f"👑 <b>Панель лидера</b> · #{t.id} {escape(t.title)}\n\n"
        f"Участников: {n}/{t.max_participants}\n"
        f"Статус: {t.status.value}\n"
    )
    if gold_waiting:
        text += f"\n⏳ Ожидается подтверждение Gold гарантом (@{SUPPORT_USERNAME})."
    elif t.gold_enabled and t.guarantor_status == "gold_confirmed":
        text += "\n✅ Фонд подтверждён гарантом. Можно собирать игроков и стартовать."
    if t.guarantor_status == "awaiting_result":
        text += "\n📸 Результат сдан — ждите обработки гарантом."

    await call.message.answer(
        text,
        reply_markup=leader_actions_kb(tid, can_start, can_submit, gold_waiting),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pt_start:"))
async def pt_start_match(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        t = (await s.execute(select(Tournament).where(Tournament.id == tid).with_for_update())).scalar_one_or_none()
        if not t or t.creator_id != u.id:
            await call.answer("Только лидер может начать", show_alert=True)
            return
        if t.gold_enabled and t.guarantor_status == "awaiting_gold":
            await call.answer("Сначала гарант должен подтвердить Gold", show_alert=True)
            return
        if t.status != TournamentStatus.open:
            await call.answer("Турнир уже не в статусе записи", show_alert=True)
            return
        n = len((await s.execute(select(Registration).where(Registration.tournament_id == tid))).scalars().all())
        if n < 2:
            await call.answer("Нужно минимум 2 участника", show_alert=True)
            return
        t.status = TournamentStatus.running
        t.registration_open = False
        await s.commit()
        title = t.title
        ids = [
            row.telegram_id
            for row in (
                await s.execute(
                    select(User).join(Registration, Registration.user_id == User.id)
                    .where(Registration.tournament_id == tid)
                )
            ).scalars().all()
        ]
    for tg_id in ids:
        try:
            await call.bot.send_message(
                tg_id,
                f"▶️ Турнир <b>{escape(title)}</b> начался!\n"
                "Ожидайте в игре, пока вас пригласят в лобби.",
            )
        except Exception:
            pass
        await asyncio.sleep(0.03)
    await call.answer("Турнир запущен!", show_alert=True)
    await call.message.answer(f"▶️ Турнир #{tid} запущен.")
    live.schedule_refresh(call.bot, tid)


@router.callback_query(F.data.startswith("pt_result:"))
async def pt_result_ask(call: CallbackQuery, state: FSMContext):
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        u = await get_or_create_user(s, call.from_user)
        t = (await s.execute(select(Tournament).where(Tournament.id == tid))).scalar_one_or_none()
        if not t or t.creator_id != u.id:
            await call.answer("Только лидер", show_alert=True)
            return
        if t.status != TournamentStatus.running:
            await call.answer("Сначала нужно начать турнир", show_alert=True)
            return
        if t.guarantor_status == "awaiting_result":
            await call.answer("Результат уже сдан", show_alert=True)
            return
    await state.set_state(PlayerResultStates.shot)
    await state.update_data(pt_result_tid=tid)
    await call.message.answer(
        "📸 Пришлите <b>скриншот статистики</b> матча одним фото.\n"
        "Гарант обработает результат.\n/cancel — отмена"
    )
    await call.answer()


@router.message(PlayerResultStates.shot, F.photo)
async def pt_result_shot(message: Message, state: FSMContext):
    d = await state.get_data()
    tid = d.get("pt_result_tid")
    if not tid:
        await state.clear()
        return
    shot = message.photo[-1].file_id
    async with SessionLocal() as s:
        u = await get_or_create_user(s, message.from_user)
        t = (await s.execute(select(Tournament).where(Tournament.id == tid).with_for_update())).scalar_one_or_none()
        if not t or t.creator_id != u.id:
            await state.clear()
            await message.answer("Нет доступа.")
            return
        t.result_screenshot = shot
        t.guarantor_status = "awaiting_result"
        await s.commit()
        title = t.title
        gold = t.gold_enabled
        prize = t.prize_pool_gold
        nick = u.nickname or u.username or str(u.telegram_id)
    await state.clear()
    await message.answer(
        "✅ Результат отправлен на обработку гаранту.\n"
        "Ожидайте завершения турнира.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )
    caption = (
        f"📸 <b>Результат турнира игрока #{tid}</b>\n"
        f"🏆 {escape(title)}\n"
        f"Лидер: {escape(nick)}\n"
        f"{'🪙 Фонд: ' + str(prize) + ' Gold' if gold else '🆓 Бесплатный'}\n\n"
        f"Завершите турнир и выдайте призы при необходимости."
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_photo(
                admin_id, shot, caption=caption, reply_markup=admin_player_result_kb(tid)
            )
        except Exception:
            try:
                await message.bot.send_message(admin_id, caption, reply_markup=admin_player_result_kb(tid))
            except Exception:
                pass
    live.schedule_refresh(message.bot, tid)


@router.message(PlayerResultStates.shot)
async def pt_result_need_photo(message: Message):
    await message.answer("Нужно именно фото. Или /cancel")


# ----- admin guarantor -----
@router.callback_query(F.data.startswith("adm_gold_ok:"))
async def adm_gold_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid).with_for_update())).scalar_one_or_none()
        if not t:
            await call.answer("Не найден", show_alert=True)
            return
        t.guarantor_status = "gold_confirmed"
        t.registration_open = True
        await s.commit()
        title = t.title
        creator_id = t.creator_id
        prize = t.prize_pool_gold
        creator_tg = None
        if creator_id:
            cu = (await s.execute(select(User).where(User.id == creator_id))).scalar_one_or_none()
            if cu:
                creator_tg = cu.telegram_id
        ids = await list_all_telegram_ids(s)
    await call.answer("Gold подтверждён, запись открыта")
    await call.message.answer(f"✅ Турнир #{tid}: фонд подтверждён, регистрация открыта.")
    if creator_tg:
        try:
            await call.bot.send_message(
                creator_tg,
                f"✅ Гарант подтвердил получение <b>{prize}</b> Gold по турниру <b>{escape(title)}</b>.\n"
                "Запись открыта — собирайте игроков и запускайте матч.",
            )
        except Exception:
            pass
    announce = (
        f"🏆 <b>Турнир на Gold открыт!</b>\n\n"
        f"<b>{escape(title)}</b> · фонд {prize} Gold\n"
        f"Запись в боте: «🏆 Турниры»"
    )
    for tg_id in ids:
        try:
            await call.bot.send_message(tg_id, announce)
        except Exception:
            pass
        await asyncio.sleep(0.04)
    live.schedule_refresh(call.bot, tid)


@router.callback_query(F.data.startswith("adm_gold_no:"))
async def adm_gold_no(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    tid = int(call.data.split(":")[1])
    async with SessionLocal() as s:
        t = (await s.execute(select(Tournament).where(Tournament.id == tid).with_for_update())).scalar_one_or_none()
        if not t:
            await call.answer("Не найден", show_alert=True)
            return
        t.status = TournamentStatus.cancelled
        t.registration_open = False
        t.guarantor_status = "done"
        await s.commit()
        creator_tg = None
        if t.creator_id:
            cu = (await s.execute(select(User).where(User.id == t.creator_id))).scalar_one_or_none()
            if cu:
                creator_tg = cu.telegram_id
        title = t.title
    await call.answer("Отклонено")
    await call.message.answer(f"❌ Турнир #{tid} отклонён и отменён.")
    if creator_tg:
        try:
            await call.bot.send_message(
                creator_tg,
                f"❌ Турнир <b>{escape(title)}</b> отклонён гарантом / отменён.",
            )
        except Exception:
            pass
    live.schedule_refresh(call.bot, tid)
