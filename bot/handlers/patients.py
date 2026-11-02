from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import card_view, send, show
from bot.keyboards import EditFieldCb, PatientCb, PatientsPageCb
from bot.services import patients as patients_svc
from bot.services.patients import EDITABLE_FIELDS, PatientInput
from bot.states import AddPatient, EditPatient, SearchPatient
from bot.validators import parse_patient_field

router = Router(name="patients")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())


# ---------- список и карточка ----------


@router.message(Command("patients"))
@router.message(F.text == texts.BTN_PATIENTS)
async def patients_list(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    await state.clear()
    page = await patients_svc.list_patients(session, doctor.id)
    await message.answer(render.patients_list(page, archived=False), reply_markup=kb.patients_list(page, False))


@router.callback_query(PatientsPageCb.filter())
async def patients_page(
    call: CallbackQuery, callback_data: PatientsPageCb, session: AsyncSession, doctor: Doctor
) -> None:
    page = await patients_svc.list_patients(session, doctor.id, callback_data.page, callback_data.archived)
    await show(call, render.patients_list(page, callback_data.archived), kb.patients_list(page, callback_data.archived))


@router.callback_query(PatientCb.filter(F.action == "open"))
async def open_card(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await show(call, *await card_view(session, doctor, patient))


@router.callback_query(PatientCb.filter(F.action.in_({"archive", "restore"})))
async def toggle_archive(
    call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor
) -> None:
    archived = callback_data.action == "archive"
    patient = await patients_svc.set_archived(session, doctor.id, callback_data.id, archived)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    text, markup = await card_view(session, doctor, patient)
    await show(call, text, markup)


# ---------- добавление ----------


@router.message(Command("add"))
@router.message(F.text == texts.BTN_ADD)
async def add_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddPatient.full_name)
    await message.answer(texts.ASK_FULL_NAME, reply_markup=kb.input_kb())


@router.message(AddPatient.full_name, F.text)
async def add_full_name(message: Message, state: FSMContext) -> None:
    ok, value, error = parse_patient_field("full_name", message.text or "")
    if not ok:
        await message.answer(error)
        return
    await state.update_data(full_name=value)
    await state.set_state(AddPatient.birth_date)
    await message.answer(texts.ASK_BIRTH_DATE, reply_markup=kb.input_kb(skip=True))


@router.message(AddPatient.birth_date, F.text)
async def add_birth_date(message: Message, state: FSMContext) -> None:
    ok, value, error = parse_patient_field("birth_date", message.text or "")
    if not ok:
        await message.answer(error)
        return
    # FSM-данные сериализуются в JSON (Redis), поэтому дата — строкой
    await state.update_data(birth_date=value.isoformat() if value else None)
    await state.set_state(AddPatient.sex)
    await message.answer(texts.ASK_SEX, reply_markup=kb.sex_kb())


@router.message(AddPatient.sex, F.text)
async def add_sex(message: Message, state: FSMContext) -> None:
    ok, value, error = parse_patient_field("sex", message.text or "")
    if not ok:
        await message.answer(error)
        return
    await state.update_data(sex=value)
    await state.set_state(AddPatient.phone)
    await message.answer(texts.ASK_PHONE, reply_markup=kb.input_kb(skip=True))


@router.message(AddPatient.phone, F.text)
async def add_phone(message: Message, state: FSMContext) -> None:
    ok, value, error = parse_patient_field("phone", message.text or "")
    if not ok:
        await message.answer(error)
        return
    await state.update_data(phone=value)
    await state.set_state(AddPatient.notes)
    await message.answer(texts.ASK_NOTES, reply_markup=kb.input_kb(skip=True))


@router.message(AddPatient.notes, F.text)
async def add_notes(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    ok, value, error = parse_patient_field("notes", message.text or "")
    if not ok:
        await message.answer(error)
        return
    data = await state.get_data()
    patient = await patients_svc.create_patient(
        session,
        doctor.id,
        PatientInput(
            full_name=data["full_name"],
            birth_date=date.fromisoformat(data["birth_date"]) if data.get("birth_date") else None,
            sex=data.get("sex"),
            phone=data.get("phone"),
            notes=value,
        ),
    )
    await state.clear()
    await message.answer(texts.PATIENT_ADDED, reply_markup=kb.main_menu())
    text, markup = await card_view(session, doctor, patient)
    await message.answer(text, reply_markup=markup)


# ---------- редактирование ----------


@router.callback_query(PatientCb.filter(F.action == "edit"))
async def edit_menu(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await show(call, texts.CHOOSE_FIELD, kb.edit_fields(callback_data.id))


@router.callback_query(EditFieldCb.filter(F.field.in_(EDITABLE_FIELDS)))
async def edit_field(
    call: CallbackQuery, callback_data: EditFieldCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.patient_id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.set_state(EditPatient.value)
    await state.update_data(patient_id=callback_data.patient_id, field=callback_data.field)
    skip = callback_data.field != "full_name"
    markup = kb.sex_kb() if callback_data.field == "sex" else kb.input_kb(skip=skip)
    await send(call, texts.FIELD_PROMPTS[callback_data.field], markup)


@router.message(EditPatient.value, F.text)
async def edit_value(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    data = await state.get_data()
    ok, value, error = parse_patient_field(data["field"], message.text or "")
    if not ok:
        await message.answer(error)
        return
    patient = await patients_svc.update_patient(session, doctor.id, data["patient_id"], data["field"], value)
    await state.clear()
    if patient is None:
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await message.answer(texts.PATIENT_UPDATED, reply_markup=kb.main_menu())
    text, markup = await card_view(session, doctor, patient)
    await message.answer(text, reply_markup=markup)


# ---------- поиск ----------


@router.message(Command("search"))
@router.message(F.text == texts.BTN_SEARCH)
async def search_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchPatient.query)
    await message.answer(texts.ASK_SEARCH, reply_markup=kb.input_kb())


@router.message(SearchPatient.query, F.text)
async def search_query(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    found = await patients_svc.search_patients(session, doctor.id, message.text or "")
    await state.clear()
    if not found:
        await message.answer(texts.SEARCH_EMPTY, reply_markup=kb.main_menu())
        return
    await message.answer(texts.SEARCH_RESULTS.format(count=len(found)), reply_markup=kb.main_menu())
    await message.answer("Выберите пациента:", reply_markup=kb.search_results(found))
