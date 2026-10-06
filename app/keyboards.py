from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu(is_admin=False):
    rows = [
        [KeyboardButton(text="🏆 Турниры"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🪙 Gold")],
        [KeyboardButton(text="💸 Вывод"), KeyboardButton(text="🎁 Промокод")],
        [KeyboardButton(text="📜 История выводов")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def profile_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Изменить Game ID", callback_data="profile:game")],
        [InlineKeyboardButton(text="🏷 Изменить NickName", callback_data="profile:nick")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]])

def tournament_list(items):
    rows = []
    for t in items:
        rows.append([InlineKeyboardButton(text=f"🏆 {t.title}", callback_data=f"tour:{t.id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def tournament_detail(tid, registered=False):
    rows = []
    if not registered:
        rows.append([InlineKeyboardButton(text="✅ Зарегистрироваться", callback_data=f"reg:{tid}")])
    rows.append([InlineKeyboardButton(text="⬅️ К турнирам", callback_data="tours")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def confirm_withdraw(wid=None):
    prefix = "wd_confirm" if wid is None else f"wd_admin_confirm:{wid}"
    cancel = "wd_cancel" if wid is None else f"wd_admin_reject:{wid}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=prefix)],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel)]
    ])

def admin_menu():
    rows = [
        [InlineKeyboardButton(text="🏆 Создать турнир", callback_data="admin:create_tour")],
        [InlineKeyboardButton(text="📋 Управление турнирами", callback_data="admin:tours")],
        [InlineKeyboardButton(text="👥 Участники", callback_data="admin:participants")],
        [InlineKeyboardButton(text="🪙 Выдать Gold", callback_data="admin:gold")],
        [InlineKeyboardButton(text="🎁 Создать промокод", callback_data="admin:promo_create")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin:promo_list")],
        [InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="admin:withdrawals")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👤 Найти игрока", callback_data="admin:find")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promo_deactivate_kb(promo_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Отключить", callback_data=f"promo_off:{promo_id}")]
    ])

def admin_tournament_actions(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Открыть", callback_data=f"adm_tour_open:{tid}"),
         InlineKeyboardButton(text="🔒 Закрыть регистрацию", callback_data=f"adm_tour_close:{tid}")],
        [InlineKeyboardButton(text="▶️ Начать", callback_data=f"adm_tour_run:{tid}"),
         InlineKeyboardButton(text="🏁 Завершить", callback_data=f"adm_tour_finish:{tid}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"adm_tour_cancel:{tid}")],
        [InlineKeyboardButton(text="👥 Участники", callback_data=f"adm_tour_part:{tid}")],
        [InlineKeyboardButton(text="🏅 Результаты", callback_data=f"adm_results:{tid}")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"adm_edit:{tid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:tours")]
    ])

def withdrawal_actions(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Выплата произведена", callback_data=f"wd_paid:{wid}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_reject:{wid}")]
    ])
