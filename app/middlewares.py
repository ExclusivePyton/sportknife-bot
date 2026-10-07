from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.enums import ChatMemberStatus
from sqlalchemy import select
from app.db import SessionLocal
from app.services import list_active_channels
from app.models import User
from app.config import settings
from app.keyboards import subscription_kb, SUPPORT_USERNAME


async def check_subscriptions(bot: Bot, user_id: int) -> list:
    async with SessionLocal() as session:
        channels = await list_active_channels(session)
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch.chat_id, user_id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                missing.append(ch)
            elif member.status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return missing


async def is_user_banned(telegram_id: int) -> tuple:
    async with SessionLocal() as session:
        u = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if u and getattr(u, "is_banned", False):
            return True, u.ban_reason
    return False, None


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            if event.data == "check_sub":
                return await handler(event, data)

        if user is None:
            return await handler(event, data)

        if user.id in settings.admin_ids:
            return await handler(event, data)

        banned, reason = await is_user_banned(user.id)
        if banned:
            text = (
                "🚫 Вы заблокированы в боте.\n\n"
                f"Причина: {reason or 'не указана'}\n\n"
                f"Для обжалования пишите в поддержку: @{SUPPORT_USERNAME}"
            )
            if isinstance(event, CallbackQuery):
                await event.answer("Вы заблокированы", show_alert=True)
                try:
                    await event.message.answer(text)
                except Exception:
                    pass
                return None
            if isinstance(event, Message):
                await event.answer(text)
                return None
            return None

        bot: Bot = data["bot"]
        missing = await check_subscriptions(bot, user.id)
        if not missing:
            return await handler(event, data)

        sub_text = (
            "🔒 Чтобы пользоваться ботом, подпишитесь на каналы ниже.\n\n"
            "После подписки нажмите «✅ Я подписался»."
        )
        if isinstance(event, CallbackQuery):
            try:
                await event.message.answer(sub_text, reply_markup=subscription_kb(missing))
            except Exception:
                pass
            await event.answer("Нужна подписка на каналы", show_alert=True)
            return None
        if isinstance(event, Message):
            await event.answer(sub_text, reply_markup=subscription_kb(missing))
            return None
        return None
