from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import send, show
from bot.keyboards import PatientCb, ReminderCb, RemindCb
from bot.services import patients as patients_svc
from bot.services import reminders as reminders_svc
from bot.states import CreateReminder
from bot.utils import fmt_dt, parse_local_datetime, utcnow
from bot.validators import MAX_SHORT_LEN, parse_short_text

router = Router(name="reminders")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())


@router.message(Command("today"))
@router.message(F.text == texts.BTN_TODAY)
async def today(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    await state.clear()
    reminders = await reminders_svc.reminders_for_day(session, doctor)
    await message.answer(render.day_plan(reminders, doctor.timezone), reply_markup=kb.main_menu())


async def _reminders_view(session: AsyncSession, doctor: Doctor) -> tuple[str, InlineKeyboardMarkup]:
    reminders = await reminders_svc.list_pending(session, doctor.id)
    return render.reminders_list(reminders, doctor.timezone), kb.reminders_list(reminders, doctor.timezone)


@router.message(Command("reminders"))
@router.message(F.text == texts.BTN_REMINDERS)
async def reminders_list(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    await state.clear()
    text, markup = await _reminders_view(session, doctor)
    await message.answer(text, reply_markup=markup)


@router.callback_query(ReminderCb.filter(F.action == "cancel"))
async def cancel_reminder(
    call: CallbackQuery, callback_data: ReminderCb, session: AsyncSession, doctor: Doctor
) -> None:
    await reminders_svc.cancel_reminder(session, doctor.id, callback_data.id)
    text, markup = await _reminders_view(session, doctor)
    await show(call, text, markup)


@router.callback_query(PatientCb.filter(F.action == "remind"))
async def remind_menu(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await show(call, texts.OFFER_REMINDER, kb.remind_options(callback_data.id))


@router.callback_query(RemindCb.filter())
async def remind_choice(
    call: CallbackQuery, callback_data: RemindCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    patient_id = callback_data.patient_id or None
    if patient_id is not None and await patients_svc.get_patient(session, doctor.id, patient_id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    back = kb.back_to_card(patient_id) if patient_id else None
    if callback_data.days == 0:
        await show(call, texts.REMINDER_SKIPPED, back)
        return
    if callback_data.days > 0:
        remind_at = reminders_svc.remind_at_in_days(doctor.timezone, callback_data.days)
        await reminders_svc.create_reminder(
            session, doctor.id, remind_at, texts.DEFAULT_REMINDER_TEXT, patient_id
        )
        await show(call, texts.REMINDER_CREATED.format(when=fmt_dt(remind_at, doctor.timezone)), back)
        return
    await state.clear()
    await state.set_state(CreateReminder.when)
    await state.update_data(patient_id=patient_id)
    await send(call, texts.ASK_REMINDER_DATE, kb.input_kb())


@router.message(CreateReminder.when, F.text)
async def reminder_when(message: Message, state: FSMContext, doctor: Doctor) -> None:
    remind_at = parse_local_datetime(
        message.text or "", doctor.timezone, reminders_svc.DEFAULT_REMINDER_TIME
    )
    if remind_at is None or remind_at <= utcnow():
        await message.answer(texts.BAD_REMINDER_DATE)
        return
    await state.update_data(remind_at=remind_at.isoformat())
    await state.set_state(CreateReminder.text)
    await message.answer(texts.ASK_REMINDER_TEXT, reply_markup=kb.input_kb(skip=True))


@router.message(CreateReminder.text, F.text)
async def reminder_text(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    if message.text == texts.BTN_SKIP:
        text: str | None = texts.DEFAULT_REMINDER_TEXT
    else:
        text = parse_short_text(message.text or "")
    if text is None:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_SHORT_LEN))
        return
    data = await state.get_data()
    remind_at = datetime.fromisoformat(data["remind_at"])
    reminder = await reminders_svc.create_reminder(session, doctor.id, remind_at, text, data.get("patient_id"))
    await state.clear()
    if reminder is None:
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await message.answer(
        texts.REMINDER_CREATED.format(when=fmt_dt(remind_at, doctor.timezone)), reply_markup=kb.main_menu()
    )
