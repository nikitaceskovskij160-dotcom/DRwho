from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import card_view, send, show
from bot.keyboards import PatientCb
from bot.services import patients as patients_svc
from bot.services import visits as visits_svc
from bot.states import AddNote
from bot.validators import MAX_TEXT_LEN, parse_long_text

router = Router(name="notes")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())


@router.callback_query(PatientCb.filter(F.action == "add_note"))
async def note_start(
    call: CallbackQuery, callback_data: PatientCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(AddNote.text)
    await state.update_data(patient_id=callback_data.id)
    await send(call, texts.ASK_NOTE, kb.input_kb())


@router.message(AddNote.text, F.text)
async def note_save(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    text = parse_long_text(message.text or "")
    if text is None:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    data = await state.get_data()
    note = await visits_svc.add_note(session, doctor.id, data["patient_id"], text)
    await state.clear()
    patient = await patients_svc.get_patient(session, doctor.id, data["patient_id"])
    if note is None or patient is None:
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await message.answer(texts.NOTE_SAVED, reply_markup=kb.main_menu())
    card_text, markup = await card_view(session, doctor, patient)
    await message.answer(card_text, reply_markup=markup)


@router.callback_query(PatientCb.filter(F.action == "notes"))
async def notes_list(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    notes = await visits_svc.list_notes(session, doctor.id, patient.id)
    await show(call, render.notes_list(patient, notes, doctor.timezone), kb.back_to_card(patient.id))
