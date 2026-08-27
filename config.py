import os
from zoneinfo import ZoneInfo


def _clean_db_url(raw: str) -> str:
    """Railway отдаёт postgresql://, asyncpg требует postgresql+asyncpg://."""
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

DATABASE_URL = _clean_db_url(
    os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./dom_running.db"
)

# ID группового чата клуба, куда постятся анонсы. Для супергрупп число отрицательное.
CLUB_CHAT_ID = int(os.environ.get("CLUB_CHAT_ID", "0"))

ADMIN_IDS = {
    int(x)
    for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",")
    if x.strip()
}

TZ = ZoneInfo(os.environ.get("CLUB_TZ", "Europe/Moscow"))

# Напоминание накануне уходит в этот час по клубному времени
EVENING_REMINDER_HOUR = int(os.environ.get("EVENING_REMINDER_HOUR", "20"))

# За сколько минут до старта открывается кнопка чек-ина
CHECKIN_OPEN_MINUTES = int(os.environ.get("CHECKIN_OPEN_MINUTES", "30"))

# Порог неактивности для метрики отвала новичков
CHURN_INACTIVE_DAYS = int(os.environ.get("CHURN_INACTIVE_DAYS", "30"))


def is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS
