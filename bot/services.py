import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import ADMIN_CHAT_ID, ADMIN_IDS, CLUB_CHAT_ID
from bot.keyboards import announcement_kb
from bot.models import Training
from bot.utils import going_users

log = logging.getLogger(__name__)

# лимит подписи под медиа в Telegram
CAPTION_LIMIT = 1024


async def send_announcement(
    bot: Bot,
    chat_id: int,
    text: str,
    media_file_id: str | None = None,
    media_type: str | None = None,
    reply_markup=None,
) -> Message:
    """Отправляет анонс: с фото, гифкой или просто текстом.

    Если текст не помещается в подпись, медиа уходит отдельным сообщением,
    а кнопки остаются на текстовом — его и считаем анонсом.
    """
    if media_file_id and len(text) <= CAPTION_LIMIT:
        if media_type == "animation":
            return await bot.send_animation(
                chat_id, media_file_id, caption=text, reply_markup=reply_markup
            )
        return await bot.send_photo(
            chat_id, media_file_id, caption=text, reply_markup=reply_markup
        )

    if media_file_id:
        try:
            if media_type == "animation":
                await bot.send_animation(chat_id, media_file_id)
            else:
                await bot.send_photo(chat_id, media_file_id)
        except TelegramBadRequest as e:
            log.warning("Медиа не отправилось: %s", e)

    return await bot.send_message(chat_id, text, reply_markup=reply_markup)


async def _edit_announcement(bot: Bot, training: Training, text: str, reply_markup):
    """Редактирует анонс независимо от того, подпись это или текст."""
    kwargs = dict(
        chat_id=training.announcement_chat_id,
        message_id=training.announcement_message_id,
    )
    has_caption = bool(training.media_file_id)
    try:
        if has_caption:
            await bot.edit_message_caption(
                caption=text, reply_markup=reply_markup, **kwargs
            )
        else:
            await bot.edit_message_text(text=text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as e:
        msg = str(e)
        if "message is not modified" in msg:
            return
        # подпись длиннее лимита или медиа ушло отдельно — пробуем как текст
        if has_caption and "message to edit" not in msg:
            try:
                await bot.edit_message_text(
                    text=text, reply_markup=reply_markup, **kwargs
                )
                return
            except TelegramBadRequest:
                pass
        log.warning("Не удалось отредактировать анонс %s: %s", training.id, e)


async def publish_announcement(
    bot: Bot, session: AsyncSession, training: Training
) -> None:
    msg = await send_announcement(
        bot,
        CLUB_CHAT_ID,
        texts.announcement(training),
        training.media_file_id,
        training.media_type,
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
        # в каналах ответ на пост может не пройти — шлём локацию отдельным постом
        try:
            await bot.send_location(
                CLUB_CHAT_ID, latitude=route.lat, longitude=route.lng
            )
        except TelegramBadRequest:
            log.warning("Не удалось отправить локацию для тренировки %s", training.id)


async def refresh_announcement(
    bot: Bot, session: AsyncSession, training: Training
) -> None:
    if not training.announcement_message_id:
        return
    await _edit_announcement(
        bot, training, texts.announcement(training), announcement_kb(training)
    )


async def strike_announcement(
    bot: Bot, session: AsyncSession, training: Training
) -> None:
    if not training.announcement_message_id:
        return
    await _edit_announcement(bot, training, texts.announcement_cancelled(training), None)


async def notify_admins(bot: Bot, text: str) -> None:
    """Тихое служебное уведомление админам."""
    targets = [ADMIN_CHAT_ID] if ADMIN_CHAT_ID else list(ADMIN_IDS)
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, disable_notification=True)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            log.info("Уведомление админу %s не доставлено: %s", chat_id, e)


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
