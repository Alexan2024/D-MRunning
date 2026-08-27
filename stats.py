from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import keyboards as kb
from bot.db import Session
from bot.utils import club_month_stats, fmt_date, get_user, to_local, user_stats

router = Router()

MONTHS_NOM = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def _month_title() -> str:
    from bot.utils import now_utc

    return MONTHS_NOM[to_local(now_utc()).month - 1]


@router.message(F.text == kb.BTN_STATS)
@router.message(Command("stats"))
async def my_stats(message: Message):
    async with Session() as session:
        user = await get_user(session, message.from_user.id)
        if user is None:
            await message.answer("Сначала регистрация — нажми /start.")
            return
        s = await user_stats(session, user.id)

    if s["total_count"] == 0:
        await message.answer(
            "Пока ни одной отметки. Статистика начнёт считаться после первой "
            "тренировки, на которой ты отметишься."
        )
        return

    lines = [
        f"<b>{_month_title()}</b>",
        f"Тренировок: {s['month_count']}",
        f"Километраж: {s['month_km']:g} км",
    ]
    if s["month_elev"]:
        lines.append(f"Набор высоты: {s['month_elev']} м")

    lines += [
        "",
        "<b>За всё время</b>",
        f"Тренировок: {s['total_count']}",
        f"Километраж: {s['total_km']:g} км",
    ]
    if s["total_elev"]:
        lines.append(f"Набор высоты: {s['total_elev']} м")
    if s["first_training"]:
        lines.append(f"Первая тренировка: {fmt_date(s['first_training'])}")

    await message.answer("\n".join(lines))


@router.message(F.text == kb.BTN_CHALLENGES)
@router.message(Command("challenges"))
async def challenges(message: Message):
    async with Session() as session:
        c = await club_month_stats(session)

    if c["trainings"] == 0:
        await message.answer("В этом месяце тренировок ещё не было.")
        return

    lines = [
        f"<b>Клуб в {_month_title().lower()}е</b>",
        "",
        f"Общий километраж: <b>{c['km']:g} км</b>",
    ]
    if c["elev"]:
        lines.append(f"Общий набор высоты: <b>{c['elev']} м</b>")
    lines += [
        f"Тренировок: {c['trainings']}",
        f"Участвовало человек: {c['people']}",
    ]

    await message.answer("\n".join(lines))
