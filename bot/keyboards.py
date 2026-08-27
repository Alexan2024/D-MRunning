from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import CancelTemplate, Route, Training
from bot.utils import fmt_datetime

BTN_CHECKIN = "✅ Я на месте"
BTN_STATS = "📊 Моя статистика"
BTN_CHALLENGES = "🏆 Челленджи"
BTN_NEXT = "🗓 Ближайшая тренировка"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEXT), KeyboardButton(text=BTN_CHECKIN)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_CHALLENGES)],
        ],
        resize_keyboard=True,
    )


def announcement_kb(training: Training, going: bool | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Иду", callback_data=f"rsvp:{training.id}")
    if training.route.map_url:
        kb.button(text="Маршрут на карте", url=training.route.map_url)
    kb.adjust(1)
    return kb.as_markup()


def checkin_kb(training_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я на месте", callback_data=f"checkin:{training_id}"
                )
            ]
        ]
    )


def checkin_choice_kb(trainings: list[Training]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in trainings:
        kb.button(
            text=f"{t.route.title} — {fmt_datetime(t.starts_at)}",
            callback_data=f"checkin:{t.id}",
        )
    kb.adjust(1)
    return kb.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новая тренировка", callback_data="adm:new_training")
    kb.button(text="🗺 Маршруты", callback_data="adm:routes")
    kb.button(text="🗓 Тренировки", callback_data="adm:trainings")
    kb.button(text="✏️ Шаблоны отмены", callback_data="adm:templates")
    kb.button(text="📈 Метрики клуба", callback_data="adm:metrics")
    kb.adjust(1)
    return kb.as_markup()


def routes_kb(routes: list[Route], prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in routes:
        kb.button(
            text=f"{r.title} · {r.distance_km:g} км",
            callback_data=f"{prefix}:{r.id}",
        )
    kb.adjust(1)
    return kb.as_markup()


def training_manage_kb(training: Training) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Список и чек-ины", callback_data=f"adm:list:{training.id}")
    kb.button(text="📤 Экспорт CSV", callback_data=f"adm:export:{training.id}")
    kb.button(text="🕓 Перенести", callback_data=f"adm:move:{training.id}")
    kb.button(text="❌ Отменить", callback_data=f"adm:cancel:{training.id}")
    kb.adjust(1)
    return kb.as_markup()


def cancel_templates_kb(
    templates: list[CancelTemplate], training_id: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in templates:
        kb.button(text=t.text, callback_data=f"adm:cancel_tpl:{training_id}:{t.id}")
    kb.button(text="✏️ Своя причина", callback_data=f"adm:cancel_custom:{training_id}")
    kb.adjust(1)
    return kb.as_markup()
