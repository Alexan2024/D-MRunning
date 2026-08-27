from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.config import is_admin


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and is_admin(user.id))
