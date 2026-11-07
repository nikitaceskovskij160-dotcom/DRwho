from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.db.models import Doctor, VisitKind
from bot.filters import IsDoctor
from bot.handlers.views import show
from bot.keyboards import DocCb, PatientCb
from bot.services import audit
from bot.services import documents as documents_svc
from bot.services import exams as exams_svc
from bot.services import patients as patients_svc
from bot.services import visits as visits_svc
from bot.utils import local_today

router = Router(name="documents")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())


@router.callback_query(PatientCb.filter(F.action == "docs"))
async def documents_menu(
    call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor
) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await show(call, texts.CHOOSE_DOCUMENT, kb.documents(callback_data.id))


@router.callback_query(DocCb.filter())
async def document(call: CallbackQuery, callback_data: DocCb, session: AsyncSession, doctor: Doctor) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.patient_id)
    if patient is None or not isinstance(call.message, Message):
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    today = local_today(doctor.timezone)
    if callback_data.kind == "primary":
        visits = await visits_svc.list_visits(session, doctor.id, patient.id, limit=1, kind=VisitKind.PRIMARY)
        if not visits:
            await call.answer(texts.DOC_NO_PRIMARY, show_alert=True)
            return
        data = documents_svc.primary_exam(doctor, patient, visits[0], today)
    elif callback_data.kind == "diary":
        visits = await visits_svc.list_visits(session, doctor.id, patient.id, limit=None, kind=VisitKind.DIARY)
        if not visits:
            await call.answer(texts.DOC_NO_DIARY, show_alert=True)
            return
        data = documents_svc.diary(doctor, patient, visits, today)
    else:
        visits = await visits_svc.list_visits(session, doctor.id, patient.id, limit=None)
        if not visits:
            await call.answer(texts.DOC_NO_VISITS, show_alert=True)
            return
        exams = await exams_svc.list_exams(session, doctor.id, patient.id, limit=None)
        data = documents_svc.medical_history(doctor, patient, visits, exams, today)
    audit.log(session, doctor.id, "export", "patient", patient.id)
    # в имени файла только id: оно видно в списках загрузок и истории чата
    await call.message.answer_document(BufferedInputFile(data, filename=f"{callback_data.kind}_{patient.id}.docx"))
    await call.answer()
