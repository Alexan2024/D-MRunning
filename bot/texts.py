from bot.models import Route, Training
from bot.utils import fmt_date, fmt_datetime, fmt_time

WELCOME = (
    "Привет! Это бот бегового клуба <b>DÖM Running</b>.\n\n"
    "Давай познакомимся. Как тебя зовут?"
)

ASK_DISTRICT = "Приятно познакомиться, {name}. Из какого ты района?"

ONBOARDING_DONE = (
    "Готово, ты в клубе.\n\n"
    "Анонсы тренировок приходят в общий чат — там же можно записаться. "
    "Накануне и за два часа до старта я пришлю напоминание.\n"
    "На месте не забудь отметиться, по этим отметкам считается статистика."
)

NO_UPCOMING = "Ближайших тренировок пока нет."


def route_line(route: Route) -> str:
    parts = [f"{route.distance_km:g} км"]
    if route.elevation_m:
        parts.append(f"набор {route.elevation_m} м")
    return " · ".join(parts)


def announcement(training: Training, going_count: int) -> str:
    route = training.route
    lines = [
        f"🏃 <b>Тренировка — {fmt_date(training.starts_at)}, "
        f"{fmt_time(training.starts_at)}</b>",
        "",
        f"<b>{route.title}</b>",
        route_line(route),
    ]
    place = "📍 " + (route.start_note or "точка старта на карте ниже")
    lines.append(place)
    lines.append("")
    lines.append(f"Идут: <b>{going_count}</b>")
    return "\n".join(lines)


def announcement_cancelled(training: Training) -> str:
    route = training.route
    return (
        f"<s>🏃 Тренировка — {fmt_date(training.starts_at)}, "
        f"{fmt_time(training.starts_at)}</s>\n\n"
        f"<s>{route.title}</s>\n\n"
        f"<b>Отменена.</b> {training.cancel_reason or ''}".strip()
    )


def reminder_evening(training: Training) -> str:
    route = training.route
    place = route.start_note or route.title
    return (
        f"Завтра в {fmt_time(training.starts_at)} — {route.title}, "
        f"{route.distance_km:g} км.\n"
        f"Старт: {place}\n\n"
        "Если планы поменялись, отметься в анонсе."
    )


def reminder_2h(training: Training) -> str:
    route = training.route
    place = route.start_note or route.title
    return (
        f"Через 2 часа — {route.title}.\n"
        f"Старт в {fmt_time(training.starts_at)}, {place}\n\n"
        "Как будешь на месте, отметься."
    )


def cancelled_notice(training: Training) -> str:
    return (
        f"Тренировка {fmt_date(training.starts_at)}, "
        f"{fmt_time(training.starts_at)} отменена.\n\n"
        f"{training.cancel_reason or ''}".strip()
    )


def moved_notice(training: Training) -> str:
    return (
        "Тренировка перенесена.\n\n"
        f"Новые дата и время: <b>{fmt_datetime(training.starts_at)}</b>\n"
        f"{training.route.title}\n\n"
        "Запись сохранена. Если не получается — отметься в анонсе."
    )
