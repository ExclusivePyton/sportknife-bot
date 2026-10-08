from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models import (
    User, Tournament, Registration, Transaction, TransactionType,
    Withdrawal, WithdrawalStatus, TournamentStatus, TournamentResult,
    PromoCode, PromoRedemption, RequiredChannel, BotSetting,
)

async def get_or_create_user(session, tg_user, referrer_telegram_id: int | None = None):
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        referred_by_id = None
        if referrer_telegram_id and referrer_telegram_id != tg_user.id:
            ref = (
                await session.execute(select(User).where(User.telegram_id == referrer_telegram_id))
            ).scalar_one_or_none()
            if ref and not getattr(ref, "is_banned", False):
                referred_by_id = ref.id
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            referred_by_id=referred_by_id,
            referral_rewarded=False,
        )
        session.add(user)
        await session.flush()
    else:
        user.username = tg_user.username
    return user

def available_balance(user: User) -> Decimal:
    return Decimal(user.balance) - Decimal(user.reserved_balance)

async def add_gold(session, user_id, amount: Decimal, tx_type, description, reference_id=None):
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    user.balance += amount
    if tx_type in (TransactionType.admin_credit, TransactionType.prize, TransactionType.promo):
        user.total_earned += amount
    session.add(Transaction(user_id=user.id, amount=amount, type=tx_type, description=description, reference_id=reference_id))
    return user

SIDES = ("T", "CT")
SIDE_NAMES = {"T": "🟠 Т (террористы)", "CT": "🔵 КТ (контр-террористы)"}
SIDE_SHORT = {"T": "🟠 Т", "CT": "🔵 КТ"}


def side_caps(tour) -> tuple[int, int]:
    """Лимит игроков за Т и за КТ. Формат AvB: A мест за Т, B мест за КТ (1v1 → 1 и 1, 5v5 → 5 и 5)."""
    try:
        parts = str(tour.format).lower().replace("х", "v").replace("x", "v").split("v")
        if len(parts) == 2:
            a, b = int(parts[0]), int(parts[1])
            if a > 0 and b > 0:
                return a, b
    except Exception:
        pass
    half = (tour.max_participants + 1) // 2
    return half, tour.max_participants - half


async def count_by_side(session, tournament_id) -> dict:
    rows = (
        await session.execute(
            select(Registration.side, func.count(Registration.id))
            .where(Registration.tournament_id == tournament_id)
            .group_by(Registration.side)
        )
    ).all()
    return {side: n for side, n in rows}


async def create_registration(session, user_id, tournament_id, side):
    if side not in SIDES:
        raise ValueError("Выберите сторону: Т или КТ")
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    if getattr(user, "is_banned", False):
        raise ValueError("Вы заблокированы и не можете регистрироваться")
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    if tour.status != TournamentStatus.open or not tour.registration_open:
        raise ValueError("Регистрация закрыта")
    existing = (await session.execute(select(Registration.id).where(Registration.user_id == user_id, Registration.tournament_id == tournament_id))).scalar_one_or_none()
    if existing:
        raise ValueError("Вы уже зарегистрированы")
    count = (await session.execute(select(func.count(Registration.id)).where(Registration.tournament_id == tournament_id))).scalar_one()
    if count >= tour.max_participants:
        raise ValueError("Турнир уже заполнен")
    t_cap, ct_cap = side_caps(tour)
    cap = t_cap if side == "T" else ct_cap
    by_side = await count_by_side(session, tournament_id)
    if by_side.get(side, 0) >= cap:
        raise ValueError(f"За {SIDE_SHORT[side]} все места заняты ({cap}/{cap}). Выберите другую сторону.")
    if not user.game_id:
        raise ValueError("Сначала укажите Game ID через /start")
    cost = Decimal(tour.registration_cost)
    if cost > 0:
        if available_balance(user) < cost:
            raise ValueError("Недостаточно доступного Gold")
        user.balance -= cost
        session.add(Transaction(user_id=user.id, amount=-cost, type=TransactionType.registration,
                                description=f"Регистрация на турнир #{tour.id}", reference_id=str(tour.id)))
    nick = user.nickname or user.username or user.game_id
    reg = Registration(user_id=user.id, tournament_id=tour.id, game_id=user.game_id, nickname=nick, side=side)
    session.add(reg)
    await session.flush()
    # после регистрации: если слоты заполнены — закрыть регистрацию
    new_count = (
        await session.execute(
            select(func.count(Registration.id)).where(Registration.tournament_id == tournament_id)
        )
    ).scalar_one()
    filled = False
    if new_count >= tour.max_participants:
        tour.registration_open = False
        filled = True
    return reg, filled


async def change_side(session, user_id, tournament_id, side):
    """Сменить сторону, пока турнир открыт (если на другой стороне есть место)."""
    if side not in SIDES:
        raise ValueError("Выберите сторону: Т или КТ")
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    if tour.status != TournamentStatus.open:
        raise ValueError("Сменить сторону уже нельзя")
    reg = (await session.execute(select(Registration).where(
        Registration.user_id == user_id, Registration.tournament_id == tournament_id))).scalar_one_or_none()
    if not reg:
        raise ValueError("Вы не зарегистрированы в этом турнире")
    if reg.side == side:
        raise ValueError("Вы уже на этой стороне")
    t_cap, ct_cap = side_caps(tour)
    cap = t_cap if side == "T" else ct_cap
    by_side = await count_by_side(session, tournament_id)
    if by_side.get(side, 0) >= cap:
        raise ValueError(f"За {SIDE_SHORT[side]} все места заняты ({cap}/{cap})")
    reg.side = side
    return reg


async def kick_player(session, tournament_id, user_id, refund: bool):
    """Админ выгоняет игрока из турнира. Возвращает (возвращённая сумма, переоткрыта ли регистрация)."""
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    if tour.status not in (TournamentStatus.open, TournamentStatus.running):
        raise ValueError("Турнир уже завершён или отменён")
    reg = (await session.execute(select(Registration).where(
        Registration.user_id == user_id, Registration.tournament_id == tournament_id))).scalar_one_or_none()
    if not reg:
        raise ValueError("Игрок уже не в турнире")
    cost = Decimal(tour.registration_cost)
    await session.delete(reg)
    await session.flush()
    refunded = Decimal(0)
    if refund and cost > 0:
        user.balance += cost
        refunded = cost
        session.add(Transaction(user_id=user.id, amount=cost, type=TransactionType.registration_refund,
                                description=f"Возврат: исключение из турнира #{tour.id}", reference_id=str(tour.id)))
    left = (await session.execute(select(func.count(Registration.id)).where(
        Registration.tournament_id == tournament_id))).scalar_one()
    reopened = False
    if tour.status == TournamentStatus.open and left < tour.max_participants and not tour.registration_open:
        tour.registration_open = True
        reopened = True
    return refunded, reopened, user


async def finish_tournament(session, tournament_id, winner_user_ids, winner_side, prize_each, screenshot):
    """Завершить турнир: отметить победителей, начислить приз каждому, обновить статистику.
    winner_side: "T" / "CT" / "manual" / None. Выполняется атомарно, повторно завершить нельзя."""
    prize_each = Decimal(prize_each)
    if prize_each < 0:
        raise ValueError("Приз не может быть отрицательным")
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    if tour.status in (TournamentStatus.finished, TournamentStatus.cancelled):
        raise ValueError("Турнир уже завершён или отменён")
    regs = (await session.execute(select(Registration).where(Registration.tournament_id == tournament_id))).scalars().all()
    reg_users = {r.user_id for r in regs}
    winners = set(winner_user_ids)
    if not winners.issubset(reg_users):
        raise ValueError("Среди победителей есть игрок, которого нет в турнире")
    # блокируем всех игроков в стабильном порядке
    users = (await session.execute(
        select(User).where(User.id.in_(sorted(reg_users))).order_by(User.id).with_for_update()
    )).scalars().all() if reg_users else []
    for u in users:
        u.tournaments_played += 1
        if u.id in winners:
            u.wins += 1
    for r in regs:
        r.is_winner = r.user_id in winners
    if prize_each > 0:
        for uid in sorted(winners):
            await add_gold(session, uid, prize_each, TransactionType.prize,
                           f"Победа в турнире #{tournament_id}", str(tournament_id))
    tour.status = TournamentStatus.finished
    tour.registration_open = False
    tour.winner_side = winner_side
    tour.result_screenshot = screenshot
    tour.finished_at = datetime.now(timezone.utc)
    return tour, regs


async def get_history(session, user_id, limit: int = 15):
    """Пополнения (админ, промокоды, призы) и выводы пользователя."""
    deposit_types = (TransactionType.admin_credit, TransactionType.promo, TransactionType.prize)
    deposits = (await session.execute(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.type.in_(deposit_types))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc()).limit(limit)
    )).scalars().all()
    withdrawals = (await session.execute(
        select(Withdrawal).where(Withdrawal.user_id == user_id)
        .order_by(Withdrawal.created_at.desc(), Withdrawal.id.desc()).limit(limit)
    )).scalars().all()
    return deposits, withdrawals


MIN_WITHDRAWAL = Decimal("2500")


async def create_withdrawal(session, user_id, amount, skin, pattern, screenshot):
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    if getattr(user, "is_banned", False):
        raise ValueError("Вы заблокированы и не можете выводить Gold")
    amount = Decimal(amount)
    if amount < MIN_WITHDRAWAL:
        raise ValueError(f"Минимальная сумма вывода — {MIN_WITHDRAWAL} Gold")
    if amount > available_balance(user):
        raise ValueError("Нельзя вывести больше доступного Gold")
    pending = (await session.execute(
        select(func.count(Withdrawal.id)).where(
            Withdrawal.user_id == user_id,
            Withdrawal.status == WithdrawalStatus.pending,
        )
    )).scalar_one()
    if pending:
        raise ValueError("У вас уже есть заявка в обработке. Дождитесь решения по ней.")
    if not (skin or "").strip():
        raise ValueError("Укажите название скина")
    if not pattern.strip():
        raise ValueError("Pattern обязателен")
    if not screenshot:
        raise ValueError("Скриншот обязателен")
    user.reserved_balance += amount
    wd = Withdrawal(user_id=user.id, amount=amount, skin_name=skin.strip(), pattern=pattern.strip(),
                    screenshot_file_id=screenshot, status=WithdrawalStatus.pending)
    session.add(wd)
    session.add(Transaction(user_id=user.id, amount=-amount, type=TransactionType.withdrawal_hold,
                            description=f"Резерв под заявку на вывод", reference_id=f"pending"))
    await session.flush()
    return wd

async def pay_withdrawal(session, withdrawal_id, admin_id):
    wd = (await session.execute(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update())).scalar_one()
    if wd.status != WithdrawalStatus.pending:
        raise ValueError("Заявка уже обработана")
    user = (await session.execute(select(User).where(User.id == wd.user_id).with_for_update())).scalar_one()
    amount = Decimal(wd.amount)
    if user.reserved_balance < amount or user.balance < amount:
        raise ValueError("Некорректный резерв/баланс")
    user.reserved_balance -= amount
    user.balance -= amount
    user.total_withdrawn += amount
    wd.status = WithdrawalStatus.paid
    wd.admin_id = admin_id
    wd.processed_at = datetime.now(timezone.utc)
    session.add(Transaction(user_id=user.id, amount=-amount, type=TransactionType.withdrawal_paid,
                            description=f"Выплата по заявке #{wd.id}", reference_id=str(wd.id)))
    return wd

async def reject_withdrawal(session, withdrawal_id, admin_id, note=None):
    wd = (await session.execute(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update())).scalar_one()
    if wd.status != WithdrawalStatus.pending:
        raise ValueError("Заявка уже обработана")
    user = (await session.execute(select(User).where(User.id == wd.user_id).with_for_update())).scalar_one()
    amount = Decimal(wd.amount)
    if user.reserved_balance < amount:
        raise ValueError("Некорректный резерв")
    user.reserved_balance -= amount
    wd.status = WithdrawalStatus.rejected
    wd.admin_id = admin_id
    wd.admin_note = note
    wd.processed_at = datetime.now(timezone.utc)
    session.add(Transaction(user_id=user.id, amount=amount, type=TransactionType.withdrawal_release,
                            description=f"Возврат резерва по заявке #{wd.id}", reference_id=str(wd.id)))
    return wd

async def apply_result(session, tournament_id, user_id, place, prize):
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    existing = (await session.execute(select(TournamentResult.id).where(
        TournamentResult.tournament_id == tournament_id, TournamentResult.place == place))).scalar_one_or_none()
    if existing:
        raise ValueError("Это место уже назначено")
    result = TournamentResult(tournament_id=tournament_id, user_id=user_id, place=place, prize=Decimal(prize))
    session.add(result)
    user.tournaments_played += 1
    if place == 1: user.wins += 1
    elif place == 2: user.second_places += 1
    elif place == 3: user.third_places += 1
    if Decimal(prize) > 0:
        await add_gold(session, user_id, Decimal(prize), TransactionType.prize,
                       f"{place} место в турнире #{tournament_id}", str(tournament_id))
    return result


async def create_promo(
    session,
    code: str,
    gold_amount: Decimal,
    max_uses: int,
    created_by: int | None = None,
    note: str | None = None,
) -> PromoCode:
    code = code.strip().upper()
    if not code or len(code) < 3:
        raise ValueError("Код слишком короткий (минимум 3 символа)")
    if gold_amount <= 0:
        raise ValueError("Сумма Gold должна быть положительной")
    if max_uses < 0:
        raise ValueError("Лимит использований не может быть отрицательным")
    existing = (
        await session.execute(select(PromoCode.id).where(PromoCode.code == code))
    ).scalar_one_or_none()
    if existing:
        raise ValueError("Такой промокод уже существует")
    promo = PromoCode(
        code=code,
        gold_amount=Decimal(gold_amount),
        max_uses=int(max_uses),
        used_count=0,
        is_active=True,
        created_by=created_by,
        note=note,
    )
    session.add(promo)
    await session.flush()
    return promo


async def redeem_promo(session, user_id: int, code: str) -> PromoCode:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user and getattr(user, "is_banned", False):
        raise ValueError("Вы заблокированы")
    """Активировать промокод. Один пользователь — один раз на код.
    Защита через FOR UPDATE + unique constraint.
    """
    code = code.strip().upper()
    promo = (
        await session.execute(
            select(PromoCode).where(PromoCode.code == code).with_for_update()
        )
    ).scalar_one_or_none()
    if promo is None:
        raise ValueError("Промокод не найден")
    if not promo.is_active:
        raise ValueError("Промокод отключён")
    if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
        raise ValueError("Лимит использований промокода исчерпан")

    already = (
        await session.execute(
            select(PromoRedemption.id).where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if already:
        raise ValueError("Вы уже использовали этот промокод")

    amount = Decimal(promo.gold_amount)
    await add_gold(
        session,
        user_id,
        amount,
        TransactionType.promo,
        f"Промокод {promo.code}",
        reference_id=str(promo.id),
    )
    promo.used_count += 1
    session.add(
        PromoRedemption(promo_id=promo.id, user_id=user_id, gold_amount=amount)
    )
    return promo


async def list_promos(session, limit: int = 30):
    result = await session.execute(
        select(PromoCode).order_by(PromoCode.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


async def deactivate_promo(session, promo_id: int) -> PromoCode:
    promo = (
        await session.execute(
            select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
        )
    ).scalar_one()
    promo.is_active = False
    return promo


async def list_active_channels(session):
    result = await session.execute(
        select(RequiredChannel).where(RequiredChannel.is_active == True).order_by(RequiredChannel.id)
    )
    return list(result.scalars().all())


async def list_all_channels(session):
    result = await session.execute(select(RequiredChannel).order_by(RequiredChannel.id))
    return list(result.scalars().all())


async def add_required_channel(session, chat_id: int, username: str | None, title: str) -> RequiredChannel:
    existing = (
        await session.execute(select(RequiredChannel).where(RequiredChannel.chat_id == chat_id))
    ).scalar_one_or_none()
    if existing:
        existing.is_active = True
        existing.username = username
        existing.title = title or existing.title
        return existing
    ch = RequiredChannel(
        chat_id=chat_id,
        username=username,
        title=title or (username or str(chat_id)),
        is_active=True,
    )
    session.add(ch)
    await session.flush()
    return ch


async def deactivate_channel(session, channel_id: int) -> RequiredChannel:
    ch = (
        await session.execute(
            select(RequiredChannel).where(RequiredChannel.id == channel_id).with_for_update()
        )
    ).scalar_one()
    ch.is_active = False
    return ch


async def cancel_registration(session, user_id, tournament_id):
    """Выход из турнира. Возврат Gold, если регистрация была платной."""
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    if tour.status not in (TournamentStatus.open, TournamentStatus.running):
        raise ValueError("Нельзя выйти: турнир уже завершён или отменён")
    if tour.status == TournamentStatus.running:
        raise ValueError("Турнир уже идёт — выход закрыт")
    if not tour.registration_open and tour.status == TournamentStatus.open:
        # разрешаем выход пока турнир open, даже если регистрация закрыта
        pass
    reg = (
        await session.execute(
            select(Registration).where(
                Registration.user_id == user_id,
                Registration.tournament_id == tournament_id,
            )
        )
    ).scalar_one_or_none()
    if not reg:
        raise ValueError("Вы не зарегистрированы в этом турнире")
    cost = Decimal(tour.registration_cost)
    await session.delete(reg)
    await session.flush()
    if cost > 0:
        user.balance += cost
        session.add(
            Transaction(
                user_id=user.id,
                amount=cost,
                type=TransactionType.registration_refund,
                description=f"Возврат за выход из турнира #{tour.id}",
                reference_id=str(tour.id),
            )
        )
    # если турнир open и есть свободный слот — снова открыть регистрацию
    left = (
        await session.execute(
            select(func.count(Registration.id)).where(Registration.tournament_id == tournament_id)
        )
    ).scalar_one()
    reopened = False
    if tour.status == TournamentStatus.open and left < tour.max_participants:
        tour.registration_open = True
        reopened = True
    return cost, reopened


async def list_all_telegram_ids(session):
    rows = (await session.execute(select(User.telegram_id))).scalars().all()
    return list(rows)


async def get_user_by_id(session, user_id: int):
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def ban_user(session, user_id: int, reason: str):
    u = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    from datetime import datetime, timezone
    u.is_banned = True
    u.ban_reason = reason
    u.banned_at = datetime.now(timezone.utc)
    return u


async def unban_user(session, user_id: int):
    u = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    u.is_banned = False
    u.ban_reason = None
    u.banned_at = None
    return u


async def list_tournament_participant_ids(session, tournament_id: int):
    rows = (
        await session.execute(
            select(User.telegram_id)
            .join(Registration, Registration.user_id == User.id)
            .where(Registration.tournament_id == tournament_id)
        )
    ).scalars().all()
    return list(rows)


async def is_game_id_taken(session, game_id: str, exclude_user_id: int | None = None) -> bool:
    q = select(User.id).where(User.game_id == game_id)
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    return (await session.execute(q.limit(1))).scalar_one_or_none() is not None


DEFAULT_REFERRAL_REWARD = Decimal("50")


async def get_setting(session, key: str, default: str = "") -> str:
    row = (await session.execute(select(BotSetting).where(BotSetting.key == key))).scalar_one_or_none()
    return row.value if row else default


async def set_setting(session, key: str, value: str) -> None:
    row = (await session.execute(select(BotSetting).where(BotSetting.key == key))).scalar_one_or_none()
    if row is None:
        session.add(BotSetting(key=key, value=value))
    else:
        row.value = value


async def get_referral_reward(session) -> Decimal:
    raw = await get_setting(session, "referral_reward", str(DEFAULT_REFERRAL_REWARD))
    try:
        return Decimal(raw)
    except Exception:
        return DEFAULT_REFERRAL_REWARD


async def set_referral_reward(session, amount: Decimal) -> None:
    if amount < 0:
        raise ValueError("Сумма не может быть отрицательной")
    await set_setting(session, "referral_reward", str(amount))


async def count_referrals(session, user_id: int) -> tuple[int, int]:
    """(всего приглашённых, сколько уже с наградой)."""
    total = (
        await session.execute(select(func.count(User.id)).where(User.referred_by_id == user_id))
    ).scalar_one()
    rewarded = (
        await session.execute(
            select(func.count(User.id)).where(
                User.referred_by_id == user_id,
                User.referral_rewarded == True,  # noqa: E712
            )
        )
    ).scalar_one()
    return int(total), int(rewarded)


async def try_complete_referral(session, user_id: int) -> tuple[bool, Decimal, int | None]:
    """Если реферал выполнил условия (подписка проверяется снаружи) — начислить пригласившему.

    Возвращает (успех, сумма, telegram_id пригласившего).
    """
    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if not user or not user.referred_by_id or user.referral_rewarded:
        return False, Decimal(0), None
    if not user.game_id:
        return False, Decimal(0), None
    if getattr(user, "is_banned", False):
        return False, Decimal(0), None

    referrer = (
        await session.execute(select(User).where(User.id == user.referred_by_id).with_for_update())
    ).scalar_one_or_none()
    if not referrer or getattr(referrer, "is_banned", False):
        return False, Decimal(0), None

    amount = await get_referral_reward(session)
    user.referral_rewarded = True
    if amount > 0:
        await add_gold(
            session,
            referrer.id,
            amount,
            TransactionType.referral,
            f"Реферал: игрок {user.telegram_id}",
            reference_id=str(user.id),
        )
    return True, amount, referrer.telegram_id
