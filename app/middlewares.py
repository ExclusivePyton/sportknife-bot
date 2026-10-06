from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.enums import ChatMemberStatus
from app.db import SessionLocal
from app.services import list_active_channels
from app.config import settings
from app.keyboards import subscription_kb


async def check_subscriptions(bot: Bot, user_id: int) -> list:
    """Вернуть список каналов, на которые пользователь НЕ подписан."""
    async with SessionLocal() as session:
        channels = await list_active_channels(session)
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch.chat_id, user_id)
            if member.status in (
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
            ):
                missing.append(ch)
            # RESTRICTED without is_member can still count as not subscribed
            elif member.status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True):
                missing.append(ch)
        except Exception:
            # Бот не админ канала / канал недоступен — считаем «не подписан»
            missing.append(ch)
    return missing


class SubscriptionMiddleware(BaseMiddleware):
    """Блокирует бота, пока пользователь не подписан на все обязательные каналы.
    Админы из ADMIN_IDS пропускаются.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
            # Пропускаем ввод Game ID на старте после подписки — обработчик сам решит
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            # Кнопка «Я подписался» всегда пропускаем
            if event.data == "check_sub":
                return await handler(event, data)

        if user is None:
            return await handler(event, data)

        if user.id in settings.admin_ids:
            return await handler(event, data)

        bot: Bot = data["bot"]
        missing = await check_subscriptions(bot, user.id)
        if not missing:
            return await handler(event, data)

        text = (
            "🔒 Чтобы пользоваться ботом, подпишитесь на каналы ниже.\n\n"
            "После подписки нажмите «✅ Я подписался»."
        )
        if isinstance(event, CallbackQuery):
            try:
                await event.message.answer(text, reply_markup=subscription_kb(missing))
            except Exception:
                pass
            await event.answer("Нужна подписка на каналы", show_alert=True)
            return None
        if isinstance(event, Message):
            await event.answer(text, reply_markup=subscription_kb(missing))
            return None
        return None
