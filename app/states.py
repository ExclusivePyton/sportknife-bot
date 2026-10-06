from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    game_id = State()
    nickname = State()

class WithdrawalStates(StatesGroup):
    amount = State()
    skin = State()
    pattern = State()
    screenshot = State()
    confirm = State()

class AdminGoldStates(StatesGroup):
    telegram_id = State()
    amount = State()
    reason = State()

class AdminFindStates(StatesGroup):
    telegram_id = State()

class TournamentCreateStates(StatesGroup):
    title = State()
    description = State()
    start_at = State()
    format = State()
    max_participants = State()
    cost = State()
    prize_fund = State()
    conditions = State()
    additional_info = State()

class ResultStates(StatesGroup):
    tournament_id = State()
    place = State()
    telegram_id = State()
    prize = State()
    confirm = State()


class PromoRedeemStates(StatesGroup):
    code = State()


class AdminPromoStates(StatesGroup):
    code = State()
    gold = State()
    max_uses = State()
    note = State()
