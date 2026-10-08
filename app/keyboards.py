from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

SUPPORT_USERNAME = "zzxdmq"


def main_menu(is_admin=False):
    rows = [
        [KeyboardButton(text="🏆 Турниры"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📜 История")],
        [KeyboardButton(text="💸 Вывод"), KeyboardButton(text="🎁 Промокод")],
        [KeyboardButton(text="👥 Рефералы"), KeyboardButton(text="📖 Правила")],
        [KeyboardButton(text="💬 Поддержка")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def profile_edit_kb(can_edit_game_id: bool = False):
    rows = []
    if can_edit_game_id:
        rows.append([InlineKeyboardButton(text="🎮 Указать Game ID", callback_data="profile:game")])
    rows.append([InlineKeyboardButton(text="🏷 Изменить NickName", callback_data="profile:nick")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]]
    )


def tournament_list(items, counts: dict | None = None):
    """counts: {tournament_id: registered_count}"""
    counts = counts or {}
    rows = []
    for t in items:
        n = counts.get(t.id, "?")
        if t.status.value == "running":
            mark = "▶️"
        else:
            mark = "🟢" if t.registration_open else "🔒"
        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {t.title} [{n}/{t.max_participants}] {t.format}",
                callback_data=f"tour:{t.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🏁 Завершённые турниры", callback_data="tours_done")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def finished_list(items):
    rows = [
        [InlineKeyboardButton(text=f"🏁 #{t.id} {t.title} {t.format}", callback_data=f"tour:{t.id}")]
        for t in items
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К турнирам", callback_data="tours")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tournament_detail(tid, registered=False, can_leave=False, can_register=False,
                      can_switch=False, has_shot=False, back="tours"):
    rows = []
    if can_register and not registered:
        rows.append([InlineKeyboardButton(text="✅ Зарегистрироваться", callback_data=f"rp:{tid}")])
    if registered and can_switch:
        rows.append([InlineKeyboardButton(text="🔄 Сменить сторону", callback_data=f"sp:{tid}")])
    if registered and can_leave:
        rows.append([InlineKeyboardButton(text="🚪 Выйти из турнира", callback_data=f"unreg:{tid}")])
    if has_shot:
        rows.append([InlineKeyboardButton(text="📸 Статистика матча", callback_data=f"shot:{tid}")])
    rows.append([InlineKeyboardButton(
        text="⬅️ К турнирам", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def side_pick_kb(tid, mode, by_side: dict, t_cap: int, ct_cap: int):
    """mode: 'reg' — выбор при регистрации, 'sw' — смена стороны."""
    prefix = "rs" if mode == "reg" else "ss"
    rows = []
    for side, cap, label in (("T", t_cap, "🟠 За Т"), ("CT", ct_cap, "🔵 За КТ")):
        n = by_side.get(side, 0)
        if n >= cap:
            rows.append([InlineKeyboardButton(text=f"🔒 {label} — занято {n}/{cap}", callback_data="side_full")])
        else:
            rows.append([InlineKeyboardButton(text=f"{label} — {n}/{cap}", callback_data=f"{prefix}:{tid}:{side}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tour:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_withdraw(wid=None):
    prefix = "wd_confirm" if wid is None else f"wd_admin_confirm:{wid}"
    cancel = "wd_cancel" if wid is None else f"wd_admin_reject:{wid}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=prefix)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel)],
        ]
    )


def admin_menu():
    rows = [
        [InlineKeyboardButton(text="🏆 Создать турнир", callback_data="admin:create_tour")],
        [InlineKeyboardButton(text="📋 Управление турнирами", callback_data="admin:tours")],
        [InlineKeyboardButton(text="👥 Участники", callback_data="admin:participants")],
        [InlineKeyboardButton(text="👥 Список игроков", callback_data="admin:users")],
        [InlineKeyboardButton(text="📣 Рассылка всем", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🎁 Создать промокод", callback_data="admin:promo_create")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin:promo_list")],
        [InlineKeyboardButton(text="📢 Обязательные каналы", callback_data="admin:channels")],
        [InlineKeyboardButton(text="👥 Реф. награда", callback_data="admin:referral")],
        [InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="admin:withdrawals")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👤 Найти игрока", callback_data="admin:find")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promo_deactivate_kb(promo_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Отключить", callback_data=f"promo_off:{promo_id}")]
        ]
    )


def admin_tours_list_kb(tours):
    """Компактный список турниров — сначала выбираешь один."""
    rows = []
    for t in tours:
        st = getattr(t.status, "value", str(t.status))
        rows.append([
            InlineKeyboardButton(
                text=f"#{t.id} {t.title} · {st}",
                callback_data=f"adm_pick:{t.id}",
            )
        ])
    if not rows:
        rows.append([InlineKeyboardButton(text="Турниров нет", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_tournament_actions(tid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Открыть", callback_data=f"adm_tour_open:{tid}"),
                InlineKeyboardButton(text="🔒 Закрыть рег.", callback_data=f"adm_tour_close:{tid}"),
            ],
            [
                InlineKeyboardButton(text="▶️ Начать", callback_data=f"adm_tour_run:{tid}"),
                InlineKeyboardButton(text="🏁 Завершить", callback_data=f"adm_tour_finish:{tid}"),
            ],
            [InlineKeyboardButton(text="❌ Отменить турнир", callback_data=f"adm_tour_cancel:{tid}")],
            [InlineKeyboardButton(text="👥 Участники", callback_data=f"adm_tour_part:{tid}")],
            [InlineKeyboardButton(text="📣 Рассылка участникам", callback_data=f"adm_tour_bc:{tid}")],
            [InlineKeyboardButton(text="⬅️ К списку турниров", callback_data="admin:tours")],
        ]
    )


def cancel_reply_kb():
    """Кнопка выхода из любого текстового ввода админа."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def withdrawal_actions(wid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Выплата произведена", callback_data=f"wd_paid:{wid}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_reject:{wid}")],
        ]
    )


def subscription_kb(channels):
    rows = []
    for ch in channels:
        title = ch.title or ch.username or str(ch.chat_id)
        if ch.username:
            url = f"https://t.me/{ch.username.lstrip('@')}"
            rows.append([InlineKeyboardButton(text=f"📢 {title}", url=url)])
        else:
            rows.append(
                [InlineKeyboardButton(text=f"📢 {title}", callback_data=f"chinfo:{ch.id}")]
            )
    rows.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_remove_kb(channel_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Убрать из обязательных", callback_data=f"ch_off:{channel_id}")]
        ]
    )


# Форматы: AvB → слоты = A + B (1 слот = 1 человек)
TOURNAMENT_FORMATS = [
    "1v1", "1v2", "1v3", "1v4", "1v5",
    "2v2", "2v3", "2v4", "2v5",
    "3v3", "3v4", "3v5",
    "4v4", "4v5",
    "5v5",
]


def slots_for_format(fmt: str) -> int:
    """1v2 → 3, 3v3 → 6 и т.д."""
    parts = fmt.lower().replace("х", "x").replace("x", "v").split("v")
    if len(parts) != 2:
        raise ValueError("Неверный формат")
    a, b = int(parts[0]), int(parts[1])
    if a < 1 or b < 1:
        raise ValueError("Неверный формат")
    return a + b


def format_choice_kb():
    rows = []
    row = []
    for fmt in TOURNAMENT_FORMATS:
        slots = slots_for_format(fmt)
        row.append(
            InlineKeyboardButton(
                text=f"{fmt} ({slots})",
                callback_data=f"fmt:{fmt}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_list_kb(users, page: int, total_pages: int):
    """users: list of User, page 0-based."""
    rows = []
    for u in users:
        label = u.game_id or "без ID"
        nick = u.nickname or u.username or "—"
        rows.append([
            InlineKeyboardButton(
                text=f"🎮 {label} | {nick} | 🪙{u.balance}",
                callback_data=f"gold_pick:{u.id}",
            )
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"users_page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"users_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="admin:user_search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def player_actions_kb(user_id: int, is_banned: bool = False):
    ban_row = (
        [InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"unban:{user_id}")]
        if is_banned
        else [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"ban:{user_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 Выдать Gold", callback_data=f"act_gold:{user_id}")],
        [InlineKeyboardButton(text="🏷 Изменить NickName", callback_data=f"edit_field:nickname:{user_id}")],
        [InlineKeyboardButton(text="🎮 Изменить Game ID", callback_data=f"edit_field:game_id:{user_id}")],
        ban_row,
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin:users")],
    ])


def finish_winner_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟠 Победила сторона Т", callback_data=f"fin_side:{tid}:T")],
        [InlineKeyboardButton(text="🔵 Победила сторона КТ", callback_data=f"fin_side:{tid}:CT")],
        [InlineKeyboardButton(text="👤 Выбрать победителей вручную", callback_data=f"fin_manual:{tid}")],
        [InlineKeyboardButton(text="➖ Без победителей", callback_data=f"fin_none:{tid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="fin_cancel")],
    ])


def finish_manual_kb(tid, regs, selected: set):
    """regs: [(reg_id, label)], selected: set reg_id"""
    rows = []
    for reg_id, label in regs:
        mark = "✅" if reg_id in selected else "⬜"
        rows.append([InlineKeyboardButton(text=f"{mark} {label}", callback_data=f"fin_tg:{tid}:{reg_id}")])
    rows.append([InlineKeyboardButton(text=f"➡️ Далее (выбрано: {len(selected)})", callback_data=f"fin_next:{tid}")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="fin_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def finish_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершить турнир", callback_data="fin_do")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="fin_cancel")],
    ])


def skip_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без скриншота", callback_data="fin_skip_shot")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="fin_cancel")],
    ])


def admin_participants_kb(tid, rows_):
    """rows_: [(user_id, label)] — кнопки исключения игроков."""
    rows = [
        [InlineKeyboardButton(text=f"🚫 Выгнать: {label}", callback_data=f"kick:{tid}:{uid}")]
        for uid, label in rows_
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def kick_confirm_kb(tid, uid, paid: bool):
    rows = []
    if paid:
        rows.append([InlineKeyboardButton(text="♻️ Выгнать и вернуть Gold", callback_data=f"kick_do:{tid}:{uid}:1")])
        rows.append([InlineKeyboardButton(text="🚫 Выгнать без возврата", callback_data=f"kick_do:{tid}:{uid}:0")])
    else:
        rows.append([InlineKeyboardButton(text="🚫 Выгнать из турнира", callback_data=f"kick_do:{tid}:{uid}:0")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm_tour_part:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
