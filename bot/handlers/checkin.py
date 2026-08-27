from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot import keyboards as kb
from bot.db import Session
from bot.models import Checkin
from bot.utils import (
    checkin_available_trainings,
    checkin_window_open,
    fmt_datetime,
    get_training,
    get_user,
)

router = Router()

NOT_REGISTERED = "Сначала пройди регистрацию — нажми /start."


@router.message(F.text == kb.BTN_CHECKIN)
@router.message(Command("checkin"))
async def checkin_menu(message: Message):
    async with Session() as session:
        user = await get_user(session, message.from_user.id)
        if user is None:
            await message.answer(NOT_REGISTERED)
            return

        items = await checkin_available_trainings(session)

    if not items:
        await message.answer(
            "Сейчас отмечаться не на чем. Кнопка открывается за полчаса до старта "
            "и работает до конца дня."
        )
        return

    if len(items) == 1:
        await _do_checkin(message, message.from_user.id, items[0].id)
        return

    await message.answer(
        "На какой тренировке отмечаешься?", reply_markup=kb.checkin_choice_kb(items)
    )


@router.callback_query(F.data.startswith("checkin:"))
async def checkin_callback(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])
    text = await _checkin_result(callback.from_user.id, training_id)
    await callback.answer(text, show_alert=True)


async def _do_checkin(message: Message, tg_id: int, training_id: int):
    text = await _checkin_result(tg_id, training_id)
    await message.answer(text)


async def _checkin_result(tg_id: int, training_id: int) -> str:
    async with Session() as session:
        user = await get_user(session, tg_id)
        if user is None:
            return NOT_REGISTERED

        training = await get_training(session, training_id)
        if training is None:
            return "Тренировка не найдена."

        if not checkin_window_open(training):
            return (
                "Окно чек-ина закрыто. Если был на тренировке — напиши админу, "
                "он отметит вручную."
            )

        existing = await session.scalar(
            select(Checkin).where(
                Checkin.user_id == user.id, Checkin.training_id == training_id
            )
        )
        if existing:
            return "Ты уже отмечен на этой тренировке."

        session.add(Checkin(user_id=user.id, training_id=training_id))
        await session.commit()

        km = training.route.distance_km
        when = fmt_datetime(training.starts_at)

    return f"Отметил: {when}, +{km:g} км. Хорошей пробежки."
