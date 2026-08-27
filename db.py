from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import DATABASE_URL
from bot.models import Base, CancelTemplate

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

DEFAULT_CANCEL_TEMPLATES = [
    "Отменяем из-за погоды.",
    "Отменяем, перенесём на другой день.",
    "Отменяем по техническим причинам.",
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as session:
        existing = await session.scalar(select(CancelTemplate).limit(1))
        if existing is None:
            for i, text in enumerate(DEFAULT_CANCEL_TEMPLATES):
                session.add(CancelTemplate(text=text, sort_order=i))
            await session.commit()
