from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import send, show
from bot.keyboards import PatientCb
from bot.services import patients as patients_svc
from bot.services import visits as visits_svc
from bot.services.visits import VisitInput
from bot.states import AddVisit
from bot.validators import MAX_TEXT_LEN, parse_long_text

router = Router(name="visits")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())

# шаг -> (поле, следующий шаг, вопрос следующего шага)
STEPS = {
    AddVisit.complaints.state: ("complaints", AddVisit.diagnosis, texts.ASK_DIAGNOSIS),
    AddVisit.diagnosis.state: ("diagnosis", AddVisit.prescriptions, texts.ASK_PRESCRIPTIONS),
    AddVisit.prescriptions.state: ("prescriptions", AddVisit.comment, texts.ASK_COMMENT),
}


@router.callback_query(PatientCb.filter(F.action == "add_visit"))
async def visit_start(
    call: CallbackQuery, callback_data: PatientCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(AddVisit.complaints)
    await state.update_data(patient_id=callback_data.id)
    await send(call, texts.ASK_COMPLAINTS, kb.input_kb(skip=True))


def _parse_step(text: str) -> tuple[bool, str | None]:
    if text == texts.BTN_SKIP:
        return True, None
    value = parse_long_text(text)
    return value is not None, value


@router.message(AddVisit.complaints, F.text)
@router.message(AddVisit.diagnosis, F.text)
@router.message(AddVisit.prescriptions, F.text)
async def visit_step(message: Message, state: FSMContext) -> None:
    ok, value = _parse_step(message.text or "")
    if not ok:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    field, next_state, question = STEPS[await state.get_state() or ""]
    await state.update_data({field: value})
    await state.set_state(next_state)
    await message.answer(question, reply_markup=kb.input_kb(skip=True))


@router.message(AddVisit.comment, F.text)
async def visit_finish(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    ok, comment = _parse_step(message.text or "")
    if not ok:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    data = await state.get_data()
    patient_id = data["patient_id"]
    visit = await visits_svc.add_visit(
        session,
        doctor.id,
        patient_id,
        VisitInput(
            complaints=data.get("complaints"),
            diagnosis=data.get("diagnosis"),
            prescriptions=data.get("prescriptions"),
            comment=comment,
        ),
    )
    await state.clear()
    if visit is None:
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await message.answer(texts.VISIT_SAVED, reply_markup=kb.main_menu())
    await message.answer(texts.OFFER_REMINDER, reply_markup=kb.remind_options(patient_id))


@router.callback_query(PatientCb.filter(F.action == "visits"))
async def visits_history(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    visits = await visits_svc.list_visits(session, doctor.id, patient.id)
    await show(call, render.visits_history(patient, visits, doctor.timezone), kb.back_to_card(patient.id))
