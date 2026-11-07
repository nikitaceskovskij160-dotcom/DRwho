"""Общие для хендлеров функции показа экранов."""

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render
from bot.db.models import Doctor, Patient
from bot.services import ai as ai_svc
from bot.services import exams as exams_svc
from bot.services import reminders as reminders_svc
from bot.services import visits as visits_svc
from bot.utils import local_today, split_text

AI_CONTEXT_LIMIT = 50


async def card_view(session: AsyncSession, doctor: Doctor, patient: Patient) -> tuple[str, InlineKeyboardMarkup]:
    visits = await visits_svc.list_visits(session, doctor.id, patient.id, limit=3)
    reminders = await reminders_svc.list_pending(session, doctor.id, patient_id=patient.id, limit=5)
    return render.patient_card(patient, visits, reminders, doctor.timezone), kb.patient_card(patient)


async def patient_context(session: AsyncSession, doctor: Doctor, patient: Patient) -> str:
    """Обезличенная выписка пациента для ИИ."""
    visits = await visits_svc.list_visits(session, doctor.id, patient.id, limit=AI_CONTEXT_LIMIT)
    notes = await visits_svc.list_notes(session, doctor.id, patient.id, limit=AI_CONTEXT_LIMIT)
    exams = await exams_svc.list_exams(session, doctor.id, patient.id, limit=AI_CONTEXT_LIMIT)
    return ai_svc.build_context(patient, visits, notes, exams, local_today(doctor.timezone))


async def send_plain(message: Message, text: str) -> None:
    """Отправляет текст без HTML-разметки, при необходимости несколькими сообщениями."""
    for chunk in split_text(text):
        await message.answer(chunk, parse_mode=None)


async def show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Заменяет содержимое сообщения с кнопками; если нельзя — отправляет новое."""
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error):
                await call.message.answer(text, reply_markup=markup)
    await call.answer()


async def send(
    call: CallbackQuery, text: str, markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None
) -> None:
    """Отправляет новое сообщение в чат, из которого нажата кнопка."""
    if isinstance(call.message, Message):
        await call.message.answer(text, reply_markup=markup)
    await call.answer()
