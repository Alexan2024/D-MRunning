import csv
import io
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from bot import keyboards as kb
from bot import texts
from bot.config import CHURN_INACTIVE_DAYS
from bot.db import Session
from bot.filters import AdminFilter
from bot.models import (
    CancelTemplate,
    Checkin,
    Rsvp,
    RsvpStatus,
    Training,
    TrainingStatus,
    User,
)
from bot.services import broadcast_going, refresh_announcement, strike_announcement
from bot.states import CancelTraining, MoveTraining, TemplateEdit
from bot.utils import (
    fmt_datetime,
    get_training,
    going_users,
    local_to_utc,
    now_utc,
    to_local,
)

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


# ---------------------------------------------------------------- список тренировок


@router.callback_query(F.data == "adm:trainings")
async def trainings_list(callback: CallbackQuery):
    async with Session() as session:
        rows = await session.scalars(
            select(Training)
            .where(Training.starts_at >= now_utc() - timedelta(days=14))
            .order_by(Training.starts_at)
            .limit(20)
        )
        items = list(rows)

    if not items:
        await callback.message.answer("Тренировок нет.", reply_markup=kb.admin_menu())
        await callback.answer()
        return

    b = InlineKeyboardBuilder()
    for t in items:
        mark = "❌ " if t.status == TrainingStatus.cancelled.value else ""
        b.button(
            text=f"{mark}{fmt_datetime(t.starts_at)} — {t.route.title}",
            callback_data=f"adm:training:{t.id}",
        )
    b.adjust(1)
    await callback.message.answer("Тренировки:", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adm:training:"))
async def training_card(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[2])
    async with Session() as session:
        training = await get_training(session, training_id)
        if training is None:
            await callback.answer("Не найдена.", show_alert=True)
            return
        going = len(await going_users(session, training_id))
        checked = (
            await session.scalar(
                select(func.count())
                .select_from(Checkin)
                .where(Checkin.training_id == training_id)
            )
        ) or 0

    text = (
        f"<b>{fmt_datetime(training.starts_at)}</b>\n"
        f"{training.route.title} · {training.route.distance_km:g} км\n"
        f"Статус: {training.status}\n\n"
        f"Записались: {going}\nОтметились: {checked}"
    )
    await callback.message.answer(text, reply_markup=kb.training_manage_kb(training))
    await callback.answer()


# ---------------------------------------------------------------- чек-ины вручную


@router.callback_query(F.data.startswith("adm:list:"))
async def training_people(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[2])

    async with Session() as session:
        rows = await session.execute(
            select(User, Rsvp.status, Checkin.id)
            .outerjoin(
                Rsvp,
                (Rsvp.user_id == User.id) & (Rsvp.training_id == training_id),
            )
            .outerjoin(
                Checkin,
                (Checkin.user_id == User.id) & (Checkin.training_id == training_id),
            )
            .where((Rsvp.id.is_not(None)) | (Checkin.id.is_not(None)))
            .order_by(User.name)
        )
        people = rows.all()

    if not people:
        await callback.message.answer("Пока никого.")
        await callback.answer()
        return

    b = InlineKeyboardBuilder()
    lines = []
    for user, rsvp_status, checkin_id in people:
        mark = "✅" if checkin_id else ("🕓" if rsvp_status == RsvpStatus.going.value else "—")
        lines.append(f"{mark} {user.name} · {user.district}")
        action = "off" if checkin_id else "on"
        b.button(
            text=f"{'Снять' if checkin_id else 'Отметить'}: {user.name}",
            callback_data=f"adm:ck_{action}:{training_id}:{user.id}",
        )
    b.adjust(1)

    await callback.message.answer(
        "✅ отметился · 🕓 записался, но не отметился\n\n" + "\n".join(lines),
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ck_on:"))
async def checkin_on(callback: CallbackQuery):
    _, _, training_id, user_id = callback.data.split(":")
    async with Session() as session:
        exists = await session.scalar(
            select(Checkin).where(
                Checkin.training_id == int(training_id),
                Checkin.user_id == int(user_id),
            )
        )
        if not exists:
            session.add(
                Checkin(
                    training_id=int(training_id),
                    user_id=int(user_id),
                    added_by_admin=True,
                )
            )
            await session.commit()
    await callback.answer("Отметил.")


@router.callback_query(F.data.startswith("adm:ck_off:"))
async def checkin_off(callback: CallbackQuery):
    _, _, training_id, user_id = callback.data.split(":")
    async with Session() as session:
        row = await session.scalar(
            select(Checkin).where(
                Checkin.training_id == int(training_id),
                Checkin.user_id == int(user_id),
            )
        )
        if row:
            await session.delete(row)
            await session.commit()
    await callback.answer("Снял отметку.")


# ---------------------------------------------------------------- экспорт


@router.callback_query(F.data.startswith("adm:export:"))
async def export_csv(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[2])

    async with Session() as session:
        training = await get_training(session, training_id)
        rows = await session.execute(
            select(User, Rsvp.status, Checkin.created_at)
            .outerjoin(
                Rsvp,
                (Rsvp.user_id == User.id) & (Rsvp.training_id == training_id),
            )
            .outerjoin(
                Checkin,
                (Checkin.user_id == User.id) & (Checkin.training_id == training_id),
            )
            .where((Rsvp.id.is_not(None)) | (Checkin.id.is_not(None)))
            .order_by(User.name)
        )
        people = rows.all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Имя", "Username", "Район", "RSVP", "Чек-ин", "Время чек-ина"])
    for user, rsvp_status, checked_at in people:
        writer.writerow(
            [
                user.name,
                f"@{user.username}" if user.username else "",
                user.district,
                "иду" if rsvp_status == RsvpStatus.going.value else "нет",
                "да" if checked_at else "нет",
                to_local(checked_at).strftime("%d.%m.%Y %H:%M") if checked_at else "",
            ]
        )

    data = buf.getvalue().encode("utf-8-sig")
    filename = f"training_{to_local(training.starts_at).strftime('%Y-%m-%d')}.csv"
    await callback.message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption=f"{training.route.title}, {fmt_datetime(training.starts_at)}",
    )
    await callback.answer()


# ---------------------------------------------------------------- отмена


@router.callback_query(F.data.startswith("adm:cancel:"))
async def cancel_start(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[2])
    async with Session() as session:
        rows = await session.scalars(
            select(CancelTemplate).order_by(CancelTemplate.sort_order)
        )
        templates = list(rows)

    await callback.message.answer(
        "Причина отмены:", reply_markup=kb.cancel_templates_kb(templates, training_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cancel_tpl:"))
async def cancel_with_template(callback: CallbackQuery):
    _, _, training_id, template_id = callback.data.split(":")
    async with Session() as session:
        template = await session.get(CancelTemplate, int(template_id))
        reason = template.text if template else ""
    delivered = await _do_cancel(callback, int(training_id), reason)
    await callback.message.answer(
        f"Отменил. Уведомлений доставлено: {delivered}.", reply_markup=kb.admin_menu()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cancel_custom:"))
async def cancel_custom(callback: CallbackQuery, state: FSMContext):
    training_id = int(callback.data.split(":")[2])
    await state.set_state(CancelTraining.custom_reason)
    await state.update_data(training_id=training_id)
    await callback.message.answer("Напиши причину одним сообщением.")
    await callback.answer()


@router.message(CancelTraining.custom_reason, F.text)
async def cancel_custom_text(message: Message, state: FSMContext):
    data = await state.get_data()
    delivered = await _do_cancel(message, data["training_id"], message.text.strip())
    await state.clear()
    await message.answer(
        f"Отменил. Уведомлений доставлено: {delivered}.", reply_markup=kb.admin_menu()
    )


async def _do_cancel(event, training_id: int, reason: str) -> int:
    bot = event.bot
    async with Session() as session:
        training = await get_training(session, training_id)
        if training is None:
            return 0
        training.status = TrainingStatus.cancelled.value
        training.cancel_reason = reason
        await session.commit()

        delivered = await broadcast_going(
            bot, session, training, texts.cancelled_notice(training)
        )
        await strike_announcement(bot, session, training)
    return delivered


# ---------------------------------------------------------------- перенос


@router.callback_query(F.data.startswith("adm:move:"))
async def move_start(callback: CallbackQuery, state: FSMContext):
    training_id = int(callback.data.split(":")[2])
    await state.set_state(MoveTraining.datetime_input)
    await state.update_data(training_id=training_id)
    await callback.message.answer(
        "Новые дата и время одним сообщением: <code>14.09 19:30</code>"
    )
    await callback.answer()


@router.message(MoveTraining.datetime_input, F.text)
async def move_apply(message: Message, state: FSMContext):
    from bot.handlers.admin import _parse_date

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Формат: <code>14.09 19:30</code>")
        return

    date = _parse_date(parts[0])
    try:
        time_part = datetime.strptime(parts[1].replace(".", ":"), "%H:%M").time()
    except ValueError:
        date = None
        time_part = None

    if date is None or time_part is None:
        await message.answer("Не разобрал. Формат: <code>14.09 19:30</code>")
        return

    new_dt = local_to_utc(datetime.combine(date, time_part))
    data = await state.get_data()

    async with Session() as session:
        training = await get_training(session, data["training_id"])
        if training is None:
            await message.answer("Тренировка не найдена.")
            await state.clear()
            return

        training.starts_at = new_dt
        training.reminder_evening_sent = False
        training.reminder_2h_sent = False
        await session.commit()

        delivered = await broadcast_going(
            message.bot, session, training, texts.moved_notice(training)
        )
        await refresh_announcement(message.bot, session, training)

    await state.clear()
    await message.answer(
        f"Перенёс на {fmt_datetime(new_dt)}. Уведомлений доставлено: {delivered}.",
        reply_markup=kb.admin_menu(),
    )


# ---------------------------------------------------------------- шаблоны отмены


@router.callback_query(F.data == "adm:templates")
async def templates_list(callback: CallbackQuery):
    async with Session() as session:
        rows = await session.scalars(
            select(CancelTemplate).order_by(CancelTemplate.sort_order)
        )
        templates = list(rows)

    b = InlineKeyboardBuilder()
    for t in templates:
        b.button(text=f"✏️ {t.text}", callback_data=f"adm:tpl_edit:{t.id}")
        b.button(text=f"🗑 {t.text}", callback_data=f"adm:tpl_del:{t.id}")
    b.button(text="➕ Добавить шаблон", callback_data="adm:tpl_new")
    b.adjust(2)

    await callback.message.answer("Шаблоны причин отмены:", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "adm:tpl_new")
async def template_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TemplateEdit.new_text)
    await callback.message.answer("Текст нового шаблона:")
    await callback.answer()


@router.message(TemplateEdit.new_text, F.text)
async def template_new_save(message: Message, state: FSMContext):
    async with Session() as session:
        max_order = (
            await session.scalar(select(func.max(CancelTemplate.sort_order))) or 0
        )
        session.add(
            CancelTemplate(text=message.text.strip(), sort_order=max_order + 1)
        )
        await session.commit()
    await state.clear()
    await message.answer("Добавил.", reply_markup=kb.admin_menu())


@router.callback_query(F.data.startswith("adm:tpl_edit:"))
async def template_edit(callback: CallbackQuery, state: FSMContext):
    template_id = int(callback.data.split(":")[2])
    await state.set_state(TemplateEdit.edit_text)
    await state.update_data(template_id=template_id)
    await callback.message.answer("Новый текст шаблона:")
    await callback.answer()


@router.message(TemplateEdit.edit_text, F.text)
async def template_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    async with Session() as session:
        template = await session.get(CancelTemplate, data["template_id"])
        if template:
            template.text = message.text.strip()
            await session.commit()
    await state.clear()
    await message.answer("Обновил.", reply_markup=kb.admin_menu())


@router.callback_query(F.data.startswith("adm:tpl_del:"))
async def template_delete(callback: CallbackQuery):
    template_id = int(callback.data.split(":")[2])
    async with Session() as session:
        template = await session.get(CancelTemplate, template_id)
        if template:
            await session.delete(template)
            await session.commit()
    await callback.answer("Удалил.")


# ---------------------------------------------------------------- метрики


@router.callback_query(F.data == "adm:metrics")
async def metrics(callback: CallbackQuery):
    now = now_utc()
    month_ago = now - timedelta(days=30)
    churn_cutoff = now - timedelta(days=CHURN_INACTIVE_DAYS)

    async with Session() as session:
        total_users = await session.scalar(select(func.count()).select_from(User)) or 0
        new_users = (
            await session.scalar(
                select(func.count()).select_from(User).where(User.created_at >= month_ago)
            )
            or 0
        )

        finished = (
            await session.scalar(
                select(func.count())
                .select_from(Training)
                .where(
                    Training.starts_at >= month_ago,
                    Training.starts_at <= now,
                    Training.status != TrainingStatus.cancelled.value,
                )
            )
            or 0
        )
        checkins_month = (
            await session.scalar(
                select(func.count())
                .select_from(Checkin)
                .join(Training, Training.id == Checkin.training_id)
                .where(Training.starts_at >= month_ago, Training.starts_at <= now)
            )
            or 0
        )
        rsvp_month = (
            await session.scalar(
                select(func.count())
                .select_from(Rsvp)
                .join(Training, Training.id == Rsvp.training_id)
                .where(
                    Training.starts_at >= month_ago,
                    Training.starts_at <= now,
                    Rsvp.status == RsvpStatus.going.value,
                )
            )
            or 0
        )

        # отвал: у кого ровно одна отметка и она старше порога
        per_user = (
            select(
                Checkin.user_id.label("uid"),
                func.count(Checkin.id).label("cnt"),
                func.max(Training.starts_at).label("last_at"),
            )
            .join(Training, Training.id == Checkin.training_id)
            .group_by(Checkin.user_id)
            .subquery()
        )
        one_and_done = (
            await session.scalar(
                select(func.count())
                .select_from(per_user)
                .where(per_user.c.cnt == 1, per_user.c.last_at < churn_cutoff)
            )
            or 0
        )
        ever_ran = (
            await session.scalar(select(func.count()).select_from(per_user)) or 0
        )

    attendance = round(checkins_month / finished, 1) if finished else 0
    gap = round(100 * (1 - checkins_month / rsvp_month)) if rsvp_month else 0
    churn = round(100 * one_and_done / ever_ran) if ever_ran else 0

    text = (
        "<b>Метрики клуба</b>\n\n"
        f"Зарегистрировано: {total_users}\n"
        f"Новых за 30 дней: {new_users}\n\n"
        f"Тренировок за 30 дней: {finished}\n"
        f"Средняя явка: {attendance} чел.\n"
        f"Разрыв RSVP → чек-ин: {gap}%\n\n"
        f"Хоть раз бежали: {ever_ran}\n"
        f"Отвал после первой: {churn}% ({one_and_done} чел.)"
    )
    await callback.message.answer(text, reply_markup=kb.admin_menu())
    await callback.answer()
