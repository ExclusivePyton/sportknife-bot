from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models import (
    User, Tournament, Registration, Transaction, TransactionType,
    Withdrawal, WithdrawalStatus, TournamentStatus, TournamentResult,
    PromoCode, PromoRedemption,
)

async def get_or_create_user(session, tg_user):
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=tg_user.id, username=tg_user.username)
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

async def create_registration(session, user_id, tournament_id):
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    tour = (await session.execute(select(Tournament).where(Tournament.id == tournament_id).with_for_update())).scalar_one()
    if tour.status != TournamentStatus.open or not tour.registration_open:
        raise ValueError("Регистрация закрыта")
    count = (await session.execute(select(func.count(Registration.id)).where(Registration.tournament_id == tournament_id))).scalar_one()
    if count >= tour.max_participants:
        raise ValueError("Турнир уже заполнен")
    existing = (await session.execute(select(Registration.id).where(Registration.user_id == user_id, Registration.tournament_id == tournament_id))).scalar_one_or_none()
    if existing:
        raise ValueError("Вы уже зарегистрированы")
    if not user.game_id or not user.nickname:
        raise ValueError("Сначала заполните Game ID и NickName в профиле")
    cost = Decimal(tour.registration_cost)
    if cost > 0:
        if available_balance(user) < cost:
            raise ValueError("Недостаточно доступного Gold")
        user.balance -= cost
        session.add(Transaction(user_id=user.id, amount=-cost, type=TransactionType.registration,
                                description=f"Регистрация на турнир #{tour.id}", reference_id=str(tour.id)))
    reg = Registration(user_id=user.id, tournament_id=tour.id, game_id=user.game_id, nickname=user.nickname)
    session.add(reg)
    return reg

async def create_withdrawal(session, user_id, amount, skin, pattern, screenshot):
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")
    if amount > available_balance(user):
        raise ValueError("Нельзя вывести больше доступного Gold")
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
