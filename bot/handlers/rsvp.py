from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.db import Session
from bot.models import Rsvp, RsvpStatus, TrainingStatus
from bot.services import refresh_announcement
from bot.utils import get_training, get_user

router = Router()


@router.callback_query(F.data.startswith("rsvp:"))
async def toggle_rsvp(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])

    async with Session() as session:
        user = await get_user(session, callback.from_user.id)

        if user is None:
            me = await callback.bot.me()
            await callback.answer(
                "Сначала короткая регистрация в боте — это одна минута.",
                show_alert=True,
                url=f"https://t.me/{me.username}?start=rsvp_{training_id}",
            )
            return

        training = await get_training(session, training_id)
        if training is None or training.status != TrainingStatus.planned.value:
            await callback.answer("Тренировка недоступна.", show_alert=True)
            return

        rsvp = await session.scalar(
            select(Rsvp).where(
                Rsvp.user_id == user.id, Rsvp.training_id == training_id
            )
        )

        if rsvp is None:
            session.add(
                Rsvp(
                    user_id=user.id,
                    training_id=training_id,
                    status=RsvpStatus.going.value,
                )
            )
            note = "Записал. Придёшь — отметься на месте."
        elif rsvp.status == RsvpStatus.going.value:
            rsvp.status = RsvpStatus.declined.value
            note = "Убрал из списка."
        else:
            rsvp.status = RsvpStatus.going.value
            note = "Снова записал."

        await session.commit()
        await refresh_announcement(callback.bot, session, training)

    await callback.answer(note)
