from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from bot import keyboards as kb
from bot import texts
from bot.db import Session
from bot.models import Rsvp, RsvpStatus, User
from bot.services import refresh_announcement
from bot.states import Onboarding
from bot.utils import (
    fmt_datetime,
    get_training,
    get_user,
    upcoming_trainings,
)

router = Router()


@router.message(CommandStart(deep_link=True))
async def start_deep(message: Message, command: CommandObject, state: FSMContext):
    payload = command.args or ""
    pending = None
    if payload.startswith("rsvp_"):
        try:
            pending = int(payload.split("_", 1)[1])
        except ValueError:
            pending = None

    async with Session() as session:
        user = await get_user(session, message.from_user.id)

    if user:
        if pending:
            await _register_rsvp(message, user_tg=message.from_user.id, training_id=pending)
        else:
            await message.answer("Ты уже в клубе.", reply_markup=kb.main_menu())
        return

    await state.set_state(Onboarding.name)
    await state.update_data(pending_rsvp=pending)
    await message.answer(texts.WELCOME)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    async with Session() as session:
        user = await get_user(session, message.from_user.id)
    if user:
        await message.answer(
            f"С возвращением, {user.name}.", reply_markup=kb.main_menu()
        )
        return
    await state.set_state(Onboarding.name)
    await state.update_data(pending_rsvp=None)
    await message.answer(texts.WELCOME)


@router.message(Onboarding.name, F.text)
async def onboarding_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) > 128:
        await message.answer("Напиши имя одним сообщением, до 128 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(Onboarding.district)
    await message.answer(texts.ASK_DISTRICT.format(name=name))


@router.message(Onboarding.district, F.text)
async def onboarding_district(message: Message, state: FSMContext):
    district = message.text.strip()
    if not district or len(district) > 128:
        await message.answer("Напиши район одним сообщением, до 128 символов.")
        return

    data = await state.get_data()
    async with Session() as session:
        user = User(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            name=data["name"],
            district=district,
        )
        session.add(user)
        await session.commit()

    await state.clear()
    await message.answer(texts.ONBOARDING_DONE, reply_markup=kb.main_menu())

    pending = data.get("pending_rsvp")
    if pending:
        await _register_rsvp(message, message.from_user.id, pending)


async def _register_rsvp(message: Message, user_tg: int, training_id: int):
    async with Session() as session:
        user = await get_user(session, user_tg)
        training = await get_training(session, training_id)
        if not user or not training:
            return
        existing = await session.scalar(
            select(Rsvp).where(
                Rsvp.user_id == user.id, Rsvp.training_id == training.id
            )
        )
        if existing is None:
            session.add(
                Rsvp(
                    user_id=user.id,
                    training_id=training.id,
                    status=RsvpStatus.going.value,
                )
            )
        else:
            existing.status = RsvpStatus.going.value
        await session.commit()
        await refresh_announcement(message.bot, session, training)
    await message.answer(
        f"Записал на тренировку {fmt_datetime(training.starts_at)}.",
        reply_markup=kb.main_menu(),
    )


@router.message(F.text == kb.BTN_NEXT)
@router.message(Command("next"))
async def next_training(message: Message):
    async with Session() as session:
        items = await upcoming_trainings(session, limit=3)
        if not items:
            await message.answer(texts.NO_UPCOMING)
            return
        lines = []
        for t in items:
            lines.append(
                f"<b>{fmt_datetime(t.starts_at)}</b>\n"
                f"{t.route.title} · {t.route.distance_km:g} км\n"
                f"📍 {t.route.start_note or '—'}"
            )
    await message.answer("\n\n".join(lines))
