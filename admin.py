from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import keyboards as kb
from bot.db import Session
from bot.filters import AdminFilter
from bot.models import Route, Training
from bot.services import publish_announcement
from bot.states import NewRoute, NewTraining
from bot.utils import (
    active_routes,
    fmt_date,
    fmt_datetime,
    local_to_utc,
    now_utc,
    to_local,
)

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

TIME_PRESETS = ["07:00", "08:00", "09:00", "10:00", "11:00", "19:00", "19:30", "20:00"]


@router.message(Command("admin"))
async def admin_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Админка DÖM Running", reply_markup=kb.admin_menu())


# ---------------------------------------------------------------- маршруты


@router.callback_query(F.data == "adm:routes")
async def routes_list(callback: CallbackQuery):
    async with Session() as session:
        routes = await active_routes(session)

    b = InlineKeyboardBuilder()
    for r in routes:
        b.button(text=f"🗑 {r.title}", callback_data=f"adm:route_off:{r.id}")
    b.button(text="➕ Новый маршрут", callback_data="adm:route_new")
    b.adjust(1)

    text = "Маршруты:\n\n" + (
        "\n".join(
            f"• <b>{r.title}</b> — {r.distance_km:g} км, набор {r.elevation_m} м"
            for r in routes
        )
        or "пока пусто"
    )
    await callback.message.answer(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adm:route_off:"))
async def route_off(callback: CallbackQuery):
    route_id = int(callback.data.split(":")[2])
    async with Session() as session:
        route = await session.get(Route, route_id)
        if route:
            route.is_active = False
            await session.commit()
    await callback.answer("Маршрут скрыт.")


@router.callback_query(F.data == "adm:route_new")
async def route_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewRoute.title)
    await callback.message.answer("Название маршрута?")
    await callback.answer()


@router.message(NewRoute.title, F.text)
async def route_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(NewRoute.location)
    await message.answer(
        "Точка старта: пришли геолокацию или координаты через запятую "
        "(например <code>55.751244, 37.618423</code>)."
    )


@router.message(NewRoute.location, F.location)
async def route_location_pin(message: Message, state: FSMContext):
    await state.update_data(
        lat=message.location.latitude, lng=message.location.longitude
    )
    await _ask_start_note(message, state)


@router.message(NewRoute.location, F.text)
async def route_location_text(message: Message, state: FSMContext):
    try:
        lat_s, lng_s = message.text.replace(" ", "").split(",")
        lat, lng = float(lat_s), float(lng_s)
    except ValueError:
        await message.answer("Не разобрал. Формат: <code>55.751244, 37.618423</code>")
        return
    await state.update_data(lat=lat, lng=lng)
    await _ask_start_note(message, state)


async def _ask_start_note(message: Message, state: FSMContext):
    await state.set_state(NewRoute.start_note)
    await message.answer(
        "Примечание к точке старта — где именно встречаемся. "
        "Или отправь <code>-</code>, чтобы пропустить."
    )


@router.message(NewRoute.start_note, F.text)
async def route_note(message: Message, state: FSMContext):
    note = message.text.strip()
    await state.update_data(start_note=None if note == "-" else note)
    await state.set_state(NewRoute.distance)
    await message.answer("Дистанция в километрах? Например <code>8</code> или <code>8.5</code>")


@router.message(NewRoute.distance, F.text)
async def route_distance(message: Message, state: FSMContext):
    try:
        distance = float(message.text.replace(",", ".").strip())
    except ValueError:
        await message.answer("Нужно число. Например <code>8.5</code>")
        return
    await state.update_data(distance=distance)
    await state.set_state(NewRoute.elevation)
    await message.answer("Набор высоты в метрах? <code>0</code>, если плоско.")


@router.message(NewRoute.elevation, F.text)
async def route_elevation(message: Message, state: FSMContext):
    try:
        elevation = int(float(message.text.replace(",", ".").strip()))
    except ValueError:
        await message.answer("Нужно целое число метров.")
        return
    await state.update_data(elevation=elevation)
    await state.set_state(NewRoute.map_url)
    await message.answer(
        "Ссылка на карту или GPX. Или <code>-</code>, чтобы пропустить."
    )


@router.message(NewRoute.map_url, F.text)
async def route_map(message: Message, state: FSMContext):
    url = message.text.strip()
    data = await state.get_data()

    async with Session() as session:
        route = Route(
            title=data["title"],
            lat=data["lat"],
            lng=data["lng"],
            start_note=data.get("start_note"),
            distance_km=data["distance"],
            elevation_m=data["elevation"],
            map_url=None if url == "-" else url,
        )
        session.add(route)
        await session.commit()

    await state.clear()
    await message.answer(
        f"Маршрут «{data['title']}» сохранён.", reply_markup=kb.admin_menu()
    )


# ------------------------------------------------- создание тренировки (4 шага)


@router.callback_query(F.data == "adm:new_training")
async def new_training(callback: CallbackQuery, state: FSMContext):
    async with Session() as session:
        routes = await active_routes(session)

    if not routes:
        await callback.message.answer(
            "Сначала заведи хотя бы один маршрут.", reply_markup=kb.admin_menu()
        )
        await callback.answer()
        return

    await state.set_state(NewTraining.route)
    await callback.message.answer(
        "<b>Шаг 1 из 4.</b> Маршрут:",
        reply_markup=kb.routes_kb(routes, "adm:pick_route"),
    )
    await callback.answer()


@router.callback_query(NewTraining.route, F.data.startswith("adm:pick_route:"))
async def pick_route(callback: CallbackQuery, state: FSMContext):
    route_id = int(callback.data.split(":")[2])
    await state.update_data(route_id=route_id)
    await state.set_state(NewTraining.date)

    b = InlineKeyboardBuilder()
    today = to_local(now_utc()).date()
    for i in range(10):
        d = today + timedelta(days=i)
        label = "сегодня" if i == 0 else "завтра" if i == 1 else fmt_date(
            local_to_utc(datetime.combine(d, datetime.min.time()))
        )
        b.button(text=label, callback_data=f"adm:pick_date:{d.isoformat()}")
    b.adjust(2)

    await callback.message.answer(
        "<b>Шаг 2 из 4.</b> Дата (или пришли текстом в формате ДД.ММ):",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(NewTraining.date, F.data.startswith("adm:pick_date:"))
async def pick_date(callback: CallbackQuery, state: FSMContext):
    await state.update_data(date=callback.data.split(":")[2])
    await _ask_time(callback.message, state)
    await callback.answer()


@router.message(NewTraining.date, F.text)
async def type_date(message: Message, state: FSMContext):
    d = _parse_date(message.text)
    if d is None:
        await message.answer("Не разобрал дату. Формат: <code>14.09</code>")
        return
    await state.update_data(date=d.isoformat())
    await _ask_time(message, state)


async def _ask_time(message: Message, state: FSMContext):
    await state.set_state(NewTraining.time)
    b = InlineKeyboardBuilder()
    for t in TIME_PRESETS:
        b.button(text=t, callback_data=f"adm:pick_time:{t}")
    b.adjust(4)
    await message.answer(
        "<b>Шаг 3 из 4.</b> Время (или пришли текстом ЧЧ:ММ):",
        reply_markup=b.as_markup(),
    )


@router.callback_query(NewTraining.time, F.data.startswith("adm:pick_time:"))
async def pick_time(callback: CallbackQuery, state: FSMContext):
    await state.update_data(time=callback.data.split(":", 2)[2])
    await _show_preview(callback.message, state)
    await callback.answer()


@router.message(NewTraining.time, F.text)
async def type_time(message: Message, state: FSMContext):
    raw = message.text.strip().replace(".", ":")
    try:
        datetime.strptime(raw, "%H:%M")
    except ValueError:
        await message.answer("Не разобрал время. Формат: <code>19:30</code>")
        return
    await state.update_data(time=raw)
    await _show_preview(message, state)


async def _show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    starts_at = _compose_dt(data["date"], data["time"])

    async with Session() as session:
        route = await session.get(Route, data["route_id"])

    await state.update_data(starts_at=starts_at.isoformat())
    await state.set_state(NewTraining.confirm)

    b = InlineKeyboardBuilder()
    b.button(text="✅ Опубликовать", callback_data="adm:publish")
    b.button(text="✖️ Отменить", callback_data="adm:abort")
    b.adjust(1)

    preview = (
        "<b>Шаг 4 из 4.</b> Проверь:\n\n"
        f"<b>{fmt_datetime(starts_at)}</b>\n"
        f"{route.title} · {route.distance_km:g} км"
        + (f", набор {route.elevation_m} м" if route.elevation_m else "")
        + f"\n📍 {route.start_note or '—'}"
    )
    await message.answer(preview, reply_markup=b.as_markup())


@router.callback_query(NewTraining.confirm, F.data == "adm:publish")
async def publish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    starts_at = datetime.fromisoformat(data["starts_at"])

    async with Session() as session:
        training = Training(
            route_id=data["route_id"],
            starts_at=starts_at,
            created_by=callback.from_user.id,
        )
        session.add(training)
        await session.commit()
        await session.refresh(training)
        await publish_announcement(callback.bot, session, training)

    await state.clear()
    await callback.message.answer(
        "Опубликовано в чате клуба.", reply_markup=kb.admin_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "adm:abort")
async def abort(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Отменил.", reply_markup=kb.admin_menu())
    await callback.answer()


# ---------------------------------------------------------------- вспомогательное


def _parse_date(raw: str):
    raw = raw.strip().replace("/", ".").replace("-", ".")
    today = to_local(now_utc()).date()
    for fmt, has_year in (("%d.%m.%Y", True), ("%d.%m.%y", True), ("%d.%m", False)):
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        if not has_year:
            parsed = parsed.replace(year=today.year)
            if parsed < today:
                parsed = parsed.replace(year=today.year + 1)
        return parsed
    return None


def _compose_dt(date_iso: str, time_str: str) -> datetime:
    d = datetime.fromisoformat(date_iso).date()
    t = datetime.strptime(time_str, "%H:%M").time()
    return local_to_utc(datetime.combine(d, t))
