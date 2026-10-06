from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, CheckConstraint, Index, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TournamentStatus(str, Enum):
    open = "open"
    running = "running"
    finished = "finished"
    cancelled = "cancelled"


class WithdrawalStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    rejected = "rejected"


class TransactionType(str, Enum):
    admin_credit = "admin_credit"
    registration = "registration"
    prize = "prize"
    withdrawal_hold = "withdrawal_hold"
    withdrawal_paid = "withdrawal_paid"
    withdrawal_release = "withdrawal_release"
    manual_debit = "manual_debit"
    promo = "promo"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_users_balance_nonnegative"),
        CheckConstraint("reserved_balance >= 0", name="ck_users_reserved_nonnegative"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    game_id: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(255))
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    reserved_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    tournaments_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    second_places: Mapped[int] = mapped_column(Integer, default=0)
    third_places: Mapped[int] = mapped_column(Integer, default=0)
    total_earned: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_withdrawn: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")
    withdrawals: Mapped[list["Withdrawal"]] = relationship(back_populates="user")
    promo_redemptions: Mapped[list["PromoRedemption"]] = relationship(back_populates="user")


class Tournament(Base):
    __tablename__ = "tournaments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    format: Mapped[str] = mapped_column(String(255))
    max_participants: Mapped[int] = mapped_column(Integer)
    registration_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    prize_fund: Mapped[str] = mapped_column(Text)
    conditions: Mapped[str] = mapped_column(Text)
    additional_info: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TournamentStatus] = mapped_column(
        SAEnum(TournamentStatus, native_enum=False, length=20),
        default=TournamentStatus.open,
    )
    registration_open: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )
    results: Mapped[list["TournamentResult"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("user_id", "tournament_id", name="uq_registration_user_tournament"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    game_id: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped["User"] = relationship(back_populates="registrations")
    tournament: Mapped["Tournament"] = relationship(back_populates="registrations")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, native_enum=False, length=40)
    )
    description: Mapped[str] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped["User"] = relationship(back_populates="transactions")


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (Index("ix_withdrawals_pending", "status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    skin_name: Mapped[str] = mapped_column(String(255))
    pattern: Mapped[str] = mapped_column(String(255))
    screenshot_file_id: Mapped[str] = mapped_column(Text)
    status: Mapped[WithdrawalStatus] = mapped_column(
        SAEnum(WithdrawalStatus, native_enum=False, length=20),
        default=WithdrawalStatus.pending,
        index=True,
    )
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    admin_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped["User"] = relationship(back_populates="withdrawals")


class TournamentResult(Base):
    __tablename__ = "tournament_results"
    __table_args__ = (UniqueConstraint("tournament_id", "place", name="uq_result_place"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    place: Mapped[int] = mapped_column(Integer)
    prize: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    tournament: Mapped["Tournament"] = relationship(back_populates="results")


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromoCode(Base):
    """Промокод: код, награда в Gold, лимит использований."""
    __tablename__ = "promo_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    gold_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    max_uses: Mapped[int] = mapped_column(Integer)  # 0 = безлимит
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)  # telegram_id админа
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str | None] = mapped_column(String(255))

    redemptions: Mapped[list["PromoRedemption"]] = relationship(
        back_populates="promo", cascade="all, delete-orphan"
    )


class PromoRedemption(Base):
    """Одно использование промокода одним пользователем."""
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_id", "user_id", name="uq_promo_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promo_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    gold_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    promo: Mapped["PromoCode"] = relationship(back_populates="redemptions")
    user: Mapped["User"] = relationship(back_populates="promo_redemptions")
