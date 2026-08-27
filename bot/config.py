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

def _chat_id(raw: str):
    """Принимает числовой ID (-1001234567890) или @username публичного канала."""
    raw = (raw or "").strip()
    if not raw:
        return 0
    if raw.startswith("@"):
        return raw
    try:
        return int(raw)
    except ValueError:
        return raw


# Куда постятся анонсы: группа или канал.
# Для супергрупп и каналов число отрицательное, вида -1001234567890.
# Для публичного канала можно указать @username.
CLUB_CHAT_ID = _chat_id(os.environ.get("CLUB_CHAT_ID", ""))

ADMIN_IDS = {
    int(x)
    for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",")
    if x.strip()
}

# Чат админов для уведомлений о записях. Если не задан, уведомления
# уходят в личку каждому из ADMIN_IDS.
ADMIN_CHAT_ID = _chat_id(os.environ.get("ADMIN_CHAT_ID", ""))

TZ = ZoneInfo(os.environ.get("CLUB_TZ", "Europe/Moscow"))

# Напоминание накануне уходит в этот час по клубному времени
EVENING_REMINDER_HOUR = int(os.environ.get("EVENING_REMINDER_HOUR", "20"))

# За сколько минут до старта открывается кнопка чек-ина
CHECKIN_OPEN_MINUTES = int(os.environ.get("CHECKIN_OPEN_MINUTES", "30"))

# Порог неактивности для метрики отвала новичков
CHURN_INACTIVE_DAYS = int(os.environ.get("CHURN_INACTIVE_DAYS", "30"))


def is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS
