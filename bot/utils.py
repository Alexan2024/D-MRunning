from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import CHECKIN_OPEN_MINUTES, TZ
from bot.models import Checkin, Route, Rsvp, RsvpStatus, Training, TrainingStatus, User

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime) -> datetime:
    """SQLite отдаёт naive datetime — считаем такие UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def to_local(dt: datetime) -> datetime:
    return aware(dt).astimezone(TZ)


def local_to_utc(dt_local_naive: datetime) -> datetime:
    return dt_local_naive.replace(tzinfo=TZ).astimezone(timezone.utc)


def fmt_date(dt: datetime) -> str:
    d = to_local(dt)
    return f"{d.day} {MONTHS_GEN[d.month - 1]} ({WEEKDAYS[d.weekday()]})"


def fmt_time(dt: datetime) -> str:
    return to_local(dt).strftime("%H:%M")


def fmt_datetime(dt: datetime) -> str:
    return f"{fmt_date(dt)}, {fmt_time(dt)}"


def checkin_window_open(training: Training, at: datetime | None = None) -> bool:
    """Открыт за CHECKIN_OPEN_MINUTES до старта и до конца локального дня старта."""
    at = at or now_utc()
    starts_at = aware(training.starts_at)
    opens = starts_at - timedelta(minutes=CHECKIN_OPEN_MINUTES)
    local_day_end = to_local(starts_at).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    closes = local_day_end.astimezone(timezone.utc)
    return opens <= at <= closes


def month_bounds_utc(ref: datetime | None = None) -> tuple[datetime, datetime]:
    ref_local = to_local(ref or now_utc())
    start_local = ref_local.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    if start_local.month == 12:
        next_local = start_local.replace(year=start_local.year + 1, month=1)
    else:
        next_local = start_local.replace(month=start_local.month + 1)
    return start_local.astimezone(timezone.utc), next_local.astimezone(timezone.utc)


async def get_user(session: AsyncSession, tg_id: int) -> User | None:
    return await session.scalar(select(User).where(User.tg_id == tg_id))


async def going_count(session: AsyncSession, training_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Rsvp)
            .where(
                Rsvp.training_id == training_id,
                Rsvp.status == RsvpStatus.going.value,
            )
        )
    ) or 0


async def going_users(session: AsyncSession, training_id: int) -> list[User]:
    rows = await session.scalars(
        select(User)
        .join(Rsvp, Rsvp.user_id == User.id)
        .where(
            Rsvp.training_id == training_id,
            Rsvp.status == RsvpStatus.going.value,
        )
    )
    return list(rows)


async def get_training(session: AsyncSession, training_id: int) -> Training | None:
    return await session.scalar(select(Training).where(Training.id == training_id))


async def upcoming_trainings(
    session: AsyncSession, limit: int = 10
) -> list[Training]:
    rows = await session.scalars(
        select(Training)
        .where(
            Training.status == TrainingStatus.planned.value,
            Training.starts_at >= now_utc() - timedelta(hours=6),
        )
        .order_by(Training.starts_at)
        .limit(limit)
    )
    return list(rows)


async def active_routes(session: AsyncSession) -> list[Route]:
    rows = await session.scalars(
        select(Route).where(Route.is_active.is_(True)).order_by(Route.title)
    )
    return list(rows)


async def checkin_available_trainings(session: AsyncSession) -> list[Training]:
    """Тренировки, на которых прямо сейчас можно отметиться."""
    now = now_utc()
    rows = await session.scalars(
        select(Training)
        .where(
            Training.status == TrainingStatus.planned.value,
            Training.starts_at >= now - timedelta(days=1),
            Training.starts_at <= now + timedelta(days=1),
        )
        .order_by(Training.starts_at)
    )
    return [t for t in rows if checkin_window_open(t, now)]


async def user_stats(session: AsyncSession, user_id: int) -> dict:
    month_start, month_end = month_bounds_utc()

    base = (
        select(
            func.count(Checkin.id),
            func.coalesce(func.sum(Route.distance_km), 0.0),
            func.coalesce(func.sum(Route.elevation_m), 0),
        )
        .select_from(Checkin)
        .join(Training, Training.id == Checkin.training_id)
        .join(Route, Route.id == Training.route_id)
        .where(Checkin.user_id == user_id)
    )

    total = (await session.execute(base)).one()
    month = (
        await session.execute(
            base.where(
                Training.starts_at >= month_start, Training.starts_at < month_end
            )
        )
    ).one()

    first = await session.scalar(
        select(func.min(Training.starts_at))
        .select_from(Checkin)
        .join(Training, Training.id == Checkin.training_id)
        .where(Checkin.user_id == user_id)
    )

    return {
        "total_count": total[0],
        "total_km": float(total[1]),
        "total_elev": int(total[2]),
        "month_count": month[0],
        "month_km": float(month[1]),
        "month_elev": int(month[2]),
        "first_training": first,
    }


async def club_month_stats(session: AsyncSession) -> dict:
    month_start, month_end = month_bounds_utc()
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Route.distance_km), 0.0),
                func.coalesce(func.sum(Route.elevation_m), 0),
                func.count(func.distinct(Checkin.user_id)),
                func.count(func.distinct(Checkin.training_id)),
            )
            .select_from(Checkin)
            .join(Training, Training.id == Checkin.training_id)
            .join(Route, Route.id == Training.route_id)
            .where(
                Training.starts_at >= month_start, Training.starts_at < month_end
            )
        )
    ).one()
    return {
        "km": float(row[0]),
        "elev": int(row[1]),
        "people": row[2],
        "trainings": row[3],
    }
