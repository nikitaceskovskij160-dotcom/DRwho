from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor, Patient
from bot.filters import IsDoctor
from bot.handlers.views import send, show
from bot.keyboards import DraftCb, PatientCb, VisitStartCb
from bot.services import patients as patients_svc
from bot.services import templates as templates_svc
from bot.services import visits as visits_svc
from bot.services.visits import KIND_STEPS, VISIT_FIELDS, VisitInput
from bot.states import AddVisit
from bot.utils import esc, truncate
from bot.validators import MAX_TEXT_LEN, parse_long_text

router = Router(name="visits")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())


def _parse_field(text: str) -> tuple[bool, str | None]:
    if text == texts.BTN_SKIP:
        return True, None
    value = parse_long_text(text)
    return value is not None, value


async def _open_draft(message: Message, patient: Patient, kind: str, fields: dict[str, str | None]) -> None:
    await message.answer(texts.DRAFT_READY, reply_markup=kb.input_kb())
    await message.answer(render.visit_draft(patient, kind, fields), reply_markup=kb.visit_draft())


@router.callback_query(PatientCb.filter(F.action == "add_visit"))
async def visit_menu(
    call: CallbackQuery, callback_data: PatientCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    templates = await templates_svc.list_templates(session, doctor.id)
    await show(call, texts.CHOOSE_VISIT, kb.visit_start(callback_data.id, templates))


@router.callback_query(VisitStartCb.filter(F.kind.in_(KIND_STEPS)))
async def visit_start(
    call: CallbackQuery, callback_data: VisitStartCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.patient_id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    if callback_data.template_id == 0:
        await state.set_state(AddVisit.step)
        await state.update_data(patient_id=patient.id, kind=callback_data.kind, fields={}, step=0)
        first_field = KIND_STEPS[callback_data.kind][0]
        await send(call, texts.VISIT_FIELD_PROMPTS[first_field], kb.input_kb(skip=True))
        return
    template = await templates_svc.get_template(session, doctor.id, callback_data.template_id)
    if template is None:
        await call.answer(texts.TEMPLATE_NOT_FOUND, show_alert=True)
        return
    fields = {field: getattr(template, field) for field in VISIT_FIELDS}
    await state.set_state(AddVisit.draft)
    await state.update_data(patient_id=patient.id, kind=template.kind, fields=fields)
    if isinstance(call.message, Message):
        await _open_draft(call.message, patient, template.kind, fields)
    await call.answer()


@router.message(AddVisit.step, F.text)
async def visit_step(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    ok, value = _parse_field(message.text or "")
    if not ok:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    data = await state.get_data()
    steps = KIND_STEPS[data["kind"]]
    fields = {**data["fields"], steps[data["step"]]: value}
    next_step = data["step"] + 1
    await state.update_data(fields=fields, step=next_step)
    if next_step < len(steps):
        await message.answer(texts.VISIT_FIELD_PROMPTS[steps[next_step]], reply_markup=kb.input_kb(skip=True))
        return
    patient = await patients_svc.get_patient(session, doctor.id, data["patient_id"])
    if patient is None:
        await state.clear()
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await state.set_state(AddVisit.draft)
    await _open_draft(message, patient, data["kind"], fields)


@router.callback_query(AddVisit.draft, DraftCb.filter(F.action == "edit"), DraftCb.filter(F.field.in_(VISIT_FIELDS)))
async def draft_edit(call: CallbackQuery, callback_data: DraftCb, state: FSMContext) -> None:
    data = await state.get_data()
    field = callback_data.field
    await state.set_state(AddVisit.field_value)
    await state.update_data(edit_field=field)
    ask = texts.DRAFT_FIELD_ASK.format(title=texts.VISIT_FIELD_TITLES[field])
    current = data["fields"].get(field)
    if current:
        ask = texts.DRAFT_FIELD_CURRENT.format(value=esc(truncate(current, MAX_TEXT_LEN))) + "\n\n" + ask
    await send(call, ask, kb.input_kb(skip=True))


@router.message(AddVisit.field_value, F.text)
async def draft_field_value(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    ok, value = _parse_field(message.text or "")
    if not ok:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    data = await state.get_data()
    fields = {**data["fields"], data["edit_field"]: value}
    patient = await patients_svc.get_patient(session, doctor.id, data["patient_id"])
    if patient is None:
        await state.clear()
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await state.update_data(fields=fields)
    await state.set_state(AddVisit.draft)
    await _open_draft(message, patient, data["kind"], fields)


@router.callback_query(AddVisit.draft, DraftCb.filter(F.action == "save"))
async def draft_save(call: CallbackQuery, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    data = await state.get_data()
    patient_id = data["patient_id"]
    fields = data["fields"]
    visit = await visits_svc.add_visit(
        session,
        doctor.id,
        patient_id,
        VisitInput(kind=data["kind"], **{field: fields.get(field) for field in VISIT_FIELDS}),
    )
    await state.clear()
    if visit is None:
        await send(call, texts.PATIENT_NOT_FOUND, kb.main_menu())
        return
    if isinstance(call.message, Message):
        await call.message.answer(texts.VISIT_SAVED, reply_markup=kb.main_menu())
        await call.message.answer(texts.OFFER_REMINDER, reply_markup=kb.remind_options(patient_id))
    await call.answer()


@router.callback_query(PatientCb.filter(F.action == "visits"))
async def visits_history(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    visits = await visits_svc.list_visits(session, doctor.id, patient.id)
    await show(call, render.visits_history(patient, visits, doctor.timezone), kb.back_to_card(patient.id))
