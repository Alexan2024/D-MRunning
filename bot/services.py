import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import CLUB_CHAT_ID
from bot.keyboards import announcement_kb
from bot.models import Training
from bot.utils import going_count, going_users

log = logging.getLogger(__name__)


async def publish_announcement(
    bot: Bot, session: AsyncSession, training: Training
) -> None:
    count = await going_count(session, training.id)
    msg = await bot.send_message(
        CLUB_CHAT_ID,
        texts.announcement(training, count),
        reply_markup=announcement_kb(training),
    )
    training.announcement_chat_id = msg.chat.id
    training.announcement_message_id = msg.message_id
    await session.commit()

    route = training.route
    try:
        await bot.send_location(
            CLUB_CHAT_ID,
            latitude=route.lat,
            longitude=route.lng,
            reply_to_message_id=msg.message_id,
        )
    except TelegramBadRequest:
        log.warning("Не удалось отправить локацию для тренировки %s", training.id)


async def refresh_announcement(
    bot: Bot, session: AsyncSession, training: Training
) -> None:
    if not training.announcement_message_id:
        return
    count = await going_count(session, training.id)
    try:
        await bot.edit_message_text(
            chat_id=training.announcement_chat_id,
            message_id=training.announcement_message_id,
            text=texts.announcement(training, count),
            reply_markup=announcement_kb(training),
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            log.warning("Не удалось обновить анонс %s: %s", training.id, e)


async def strike_announcement(
    bot: Bot, session: AsyncSession, training: Training
) -> None:
    if not training.announcement_message_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=training.announcement_chat_id,
            message_id=training.announcement_message_id,
            text=texts.announcement_cancelled(training),
            reply_markup=None,
        )
    except TelegramBadRequest as e:
        log.warning("Не удалось перечеркнуть анонс %s: %s", training.id, e)


async def broadcast_going(
    bot: Bot,
    session: AsyncSession,
    training: Training,
    text: str,
    reply_markup=None,
) -> int:
    """Личная рассылка всем, кто нажал «Иду». Возвращает число доставленных."""
    users = await going_users(session, training.id)
    delivered = 0
    for user in users:
        try:
            await bot.send_message(user.tg_id, text, reply_markup=reply_markup)
            delivered += 1
        except TelegramForbiddenError:
            log.info("Пользователь %s заблокировал бота", user.tg_id)
        except TelegramBadRequest as e:
            log.warning("Не доставлено %s: %s", user.tg_id, e)
        await asyncio.sleep(0.05)  # ~20 сообщений в секунду
    return delivered
