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
    """Check if user is authorized (admin or in users table)"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return

        is_admin = user.id == settings.admin_id
        if is_admin or await db.is_authorized(user.id):
            data["is_admin"] = is_admin
            return await handler(event, data)

        # Not authorized
        if isinstance(event, Message):
            await event.answer(
                "🔒 <b>Доступ закрыт</b>\n\n"
                "Обратитесь к администратору для получения доступа.\n"
                f"Ваш Telegram ID: <code>{user.id}</code>",
                parse_mode="HTML"
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("🔒 Доступ закрыт", show_alert=True)
