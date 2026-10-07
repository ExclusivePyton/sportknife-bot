from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

SUPPORT_USERNAME = "zzxdmq"


def main_menu(is_admin=False):
    rows = [
        [KeyboardButton(text="🏆 Турниры"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🪙 Gold")],
        [KeyboardButton(text="💸 Вывод"), KeyboardButton(text="🎁 Промокод")],
        [KeyboardButton(text="📜 История выводов"), KeyboardButton(text="💬 Поддержка")],
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


def tournament_list(items):
    rows = []
    for t in items:
        rows.append([InlineKeyboardButton(text=f"🏆 {t.title}", callback_data=f"tour:{t.id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tournament_detail(tid, registered=False, can_leave=False):
    rows = []
    if not registered:
        rows.append([InlineKeyboardButton(text="✅ Зарегистрироваться", callback_data=f"reg:{tid}")])
    elif can_leave:
        rows.append([InlineKeyboardButton(text="🚪 Выйти из турнира", callback_data=f"unreg:{tid}")])
    rows.append([InlineKeyboardButton(text="⬅️ К турнирам", callback_data="tours")])
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
        [InlineKeyboardButton(text="🎁 Создать промокод", callback_data="admin:promo_create")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin:promo_list")],
        [InlineKeyboardButton(text="📢 Обязательные каналы", callback_data="admin:channels")],
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


def admin_tournament_actions(tid):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Открыть", callback_data=f"adm_tour_open:{tid}"),
                InlineKeyboardButton(text="🔒 Закрыть регистрацию", callback_data=f"adm_tour_close:{tid}"),
            ],
            [
                InlineKeyboardButton(text="▶️ Начать", callback_data=f"adm_tour_run:{tid}"),
                InlineKeyboardButton(text="🏁 Завершить", callback_data=f"adm_tour_finish:{tid}"),
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"adm_tour_cancel:{tid}")],
            [InlineKeyboardButton(text="👥 Участники", callback_data=f"adm_tour_part:{tid}")],
            [InlineKeyboardButton(text="📣 Рассылка участникам", callback_data=f"adm_tour_bc:{tid}")],
            [InlineKeyboardButton(text="🏅 Результаты", callback_data=f"adm_results:{tid}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:tours")],
        ]
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
