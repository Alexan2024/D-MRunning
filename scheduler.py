import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from bot import texts
from bot.config import EVENING_REMINDER_HOUR, TZ
from bot.db import Session
from bot.keyboards import checkin_kb
from bot.models import Training, TrainingStatus
from bot.services import broadcast_going
from bot.utils import aware, now_utc, to_local

log = logging.getLogger(__name__)


async def tick(bot: Bot) -> None:
    """Раз в минуту проверяем, кому пора слать напоминания."""
    now = now_utc()

    async with Session() as session:
        rows = await session.scalars(
            select(Training).where(
                Training.status == TrainingStatus.planned.value,
                Training.starts_at >= now - timedelta(hours=1),
                Training.starts_at <= now + timedelta(days=3),
            )
        )
        trainings = list(rows)

        for training in trainings:
            try:
                if not training.reminder_evening_sent and _evening_due(training, now):
                    await broadcast_going(
                        bot, session, training, texts.reminder_evening(training)
                    )
                    training.reminder_evening_sent = True
                    await session.commit()

                if not training.reminder_2h_sent and _two_hours_due(training, now):
                    await broadcast_going(
                        bot,
                        session,
                        training,
                        texts.reminder_2h(training),
                        reply_markup=checkin_kb(training.id),
                    )
                    training.reminder_2h_sent = True
                    await session.commit()
            except Exception:  # noqa: BLE001
                log.exception("Ошибка напоминания для тренировки %s", training.id)


def _evening_due(training: Training, now: datetime) -> bool:
    """20:00 по клубному времени накануне дня тренировки."""
    starts_at = aware(training.starts_at)
    start_local = to_local(starts_at)
    fire_local = (start_local - timedelta(days=1)).replace(
        hour=EVENING_REMINDER_HOUR, minute=0, second=0, microsecond=0
    )
    fire_utc = fire_local.astimezone(timezone.utc)
    # не шлём, если момент давно прошёл (тренировка создана позже)
    return fire_utc <= now < starts_at - timedelta(hours=2)


def _two_hours_due(training: Training, now: datetime) -> bool:
    starts_at = aware(training.starts_at)
    fire = starts_at - timedelta(hours=2)
    return fire <= now < starts_at


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        tick,
        "interval",
        minutes=1,
        args=[bot],
        max_instances=1,
        coalesce=True,
        id="reminders",
    )
    return scheduler
