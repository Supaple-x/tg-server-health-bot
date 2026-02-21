"""
Authentication middleware for Telegram bot
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from config import settings
from database.db import db

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Auto-register users and check if banned"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return

        # Check if user is banned
        if await db.is_banned(user.id):
            if isinstance(event, Message):
                await event.answer(
                    "🚫 <b>Доступ заблокирован</b>\n\n"
                    "Обратитесь к администратору.",
                    parse_mode="HTML"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Доступ заблокирован", show_alert=True)
            return

        # Auto-register new users
        is_admin = user.id == settings.admin_id
        if not is_admin:
            await db.ensure_user(user.id, user.username)

        data["is_admin"] = is_admin
        return await handler(event, data)
