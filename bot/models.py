from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingStatus(str, Enum):
    planned = "planned"
    cancelled = "cancelled"
    finished = "finished"


class RsvpStatus(str, Enum):
    going = "going"
    declined = "declined"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    district: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    start_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance_km: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[int] = mapped_column(Integer, default=0)
    map_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # текстовое описание маршрута: доп. точки, покрытие, где вода
    waypoints: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Training(Base):
    __tablename__ = "trainings"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default=TrainingStatus.planned.value)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # оформление анонса
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)

    announcement_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    announcement_message_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # служебные флаги планировщика
    reminder_evening_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_2h_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    route: Mapped[Route] = relationship(lazy="joined")


class Rsvp(Base):
    __tablename__ = "rsvp"
    __table_args__ = (UniqueConstraint("user_id", "training_id", name="uq_rsvp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    training_id: Mapped[int] = mapped_column(ForeignKey("trainings.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=RsvpStatus.going.value)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("user_id", "training_id", name="uq_checkin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    training_id: Mapped[int] = mapped_column(ForeignKey("trainings.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    added_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class CancelTemplate(Base):
    __tablename__ = "cancel_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
