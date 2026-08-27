import logging

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import DATABASE_URL
from bot.models import Base, CancelTemplate

log = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

DEFAULT_CANCEL_TEMPLATES = [
    "Отменяем из-за погоды.",
    "Отменяем, перенесём на другой день.",
    "Отменяем по техническим причинам.",
]

# Колонки, добавленные после первого релиза. create_all не дописывает их
# в уже существующие таблицы, поэтому доливаем вручную при старте.
ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "routes": {
        "waypoints": "TEXT",
    },
    "trainings": {
        "description": "TEXT",
        "media_file_id": "VARCHAR(256)",
        "media_type": "VARCHAR(16)",
    },
}


def _missing_columns(sync_conn):
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    missing = []
    for table, columns in ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # таблицы ещё нет — create_all создаст её сразу полной
        present = {c["name"] for c in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in present:
                missing.append((table, name, sql_type))
    return missing


async def migrate() -> None:
    async with engine.begin() as conn:
        missing = await conn.run_sync(_missing_columns)
        for table, name, sql_type in missing:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
            )
            log.info("Добавлена колонка %s.%s", table, name)


async def init_db() -> None:
    # порядок важен: сначала долить колонки в старые таблицы, затем create_all
    await migrate()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as session:
        existing = await session.scalar(select(CancelTemplate).limit(1))
        if existing is None:
            for i, tpl in enumerate(DEFAULT_CANCEL_TEMPLATES):
                session.add(CancelTemplate(text=tpl, sort_order=i))
            await session.commit()
