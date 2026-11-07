from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import patient_context, send, send_plain, show
from bot.keyboards import ExamCb, PatientCb
from bot.services import exams as exams_svc
from bot.services import patients as patients_svc
from bot.services.ai import ANALYZE_PROMPT, SUPPORTED_MIME, AiClient, AiError, Attachment, build_messages
from bot.states import AddExam
from bot.validators import MAX_TEXT_LEN, parse_long_text, parse_short_text

router = Router(name="exams")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())

# Фото и документ в Telegram — разные типы файлов, их нельзя переслать одним методом
PHOTO_MIME = "photo"
MAX_FILE_SIZE = 20 * 1024 * 1024


@router.callback_query(PatientCb.filter(F.action == "exams"))
async def exams_list(call: CallbackQuery, callback_data: PatientCb, session: AsyncSession, doctor: Doctor) -> None:
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    exams = await exams_svc.list_exams(session, doctor.id, patient.id)
    await show(call, render.exams_list(patient, exams), kb.exams_list(patient.id, exams))


@router.callback_query(PatientCb.filter(F.action == "add_exam"))
async def exam_start(
    call: CallbackQuery, callback_data: PatientCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    if await patients_svc.get_patient(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(AddExam.title)
    await state.update_data(patient_id=callback_data.id)
    await send(call, texts.ASK_EXAM_TITLE, kb.input_kb())


@router.message(AddExam.title, F.text)
async def exam_title(message: Message, state: FSMContext) -> None:
    title = parse_short_text(message.text or "")
    if title is None:
        await message.answer(texts.BAD_TEMPLATE_TITLE)
        return
    await state.update_data(title=title)
    await state.set_state(AddExam.content)
    await message.answer(texts.ASK_EXAM_CONTENT, reply_markup=kb.input_kb())


async def _save_exam(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    doctor: Doctor,
    text: str | None = None,
    file_id: str | None = None,
    file_mime: str | None = None,
) -> None:
    data = await state.get_data()
    exam = await exams_svc.add_exam(session, doctor.id, data["patient_id"], data["title"], text, file_id, file_mime)
    await state.clear()
    if exam is None:
        await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await message.answer(texts.EXAM_SAVED, reply_markup=kb.main_menu())
    await message.answer(render.exam_card(exam, doctor.timezone), reply_markup=kb.exam_card(exam))


@router.message(AddExam.content, F.text)
async def exam_text(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    text = parse_long_text(message.text or "")
    if text is None:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    await _save_exam(message, state, session, doctor, text=text)


@router.message(AddExam.content, F.photo)
async def exam_photo(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    photo = (message.photo or [])[-1]
    caption = parse_long_text(message.caption or "")
    await _save_exam(message, state, session, doctor, text=caption, file_id=photo.file_id, file_mime=PHOTO_MIME)


@router.message(AddExam.content, F.document)
async def exam_document(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    document = message.document
    if (
        document is None
        or document.mime_type not in SUPPORTED_MIME
        or (document.file_size or 0) > MAX_FILE_SIZE
    ):
        await message.answer(texts.BAD_EXAM_FILE)
        return
    caption = parse_long_text(message.caption or "")
    await _save_exam(
        message, state, session, doctor, text=caption, file_id=document.file_id, file_mime=document.mime_type
    )


@router.callback_query(ExamCb.filter(F.action == "open"))
async def exam_open(call: CallbackQuery, callback_data: ExamCb, session: AsyncSession, doctor: Doctor) -> None:
    exam = await exams_svc.get_exam(session, doctor.id, callback_data.id)
    if exam is None:
        await call.answer(texts.EXAM_NOT_FOUND, show_alert=True)
        return
    await show(call, render.exam_card(exam, doctor.timezone), kb.exam_card(exam))


@router.callback_query(ExamCb.filter(F.action == "file"))
async def exam_file(call: CallbackQuery, callback_data: ExamCb, session: AsyncSession, doctor: Doctor) -> None:
    exam = await exams_svc.get_exam(session, doctor.id, callback_data.id)
    if exam is None or exam.file_id is None:
        await call.answer(texts.EXAM_NOT_FOUND, show_alert=True)
        return
    if isinstance(call.message, Message):
        if exam.file_mime == PHOTO_MIME:
            await call.message.answer_photo(exam.file_id)
        else:
            await call.message.answer_document(exam.file_id)
    await call.answer()


@router.callback_query(ExamCb.filter(F.action == "analyze"))
async def exam_analyze(
    call: CallbackQuery,
    callback_data: ExamCb,
    session: AsyncSession,
    doctor: Doctor,
    bot: Bot,
    ai: AiClient | None = None,
) -> None:
    if ai is None:
        await call.answer(texts.AI_DISABLED, show_alert=True)
        return
    exam = await exams_svc.get_exam(session, doctor.id, callback_data.id)
    patient = await patients_svc.get_patient(session, doctor.id, exam.patient_id) if exam else None
    if exam is None or patient is None or not isinstance(call.message, Message):
        await call.answer(texts.EXAM_NOT_FOUND, show_alert=True)
        return
    await call.answer()
    await call.message.answer(texts.AI_THINKING)

    attachment = None
    if exam.file_id and exam.file_mime:
        buffer = await bot.download(exam.file_id)
        if buffer is not None:
            mime = "image/jpeg" if exam.file_mime == PHOTO_MIME else exam.file_mime
            attachment = Attachment(mime=mime, data=buffer.read())

    context = await patient_context(session, doctor, patient)
    messages = build_messages(context, [], ANALYZE_PROMPT.format(title=exam.title), attachment)
    # отпускаем соединение с БД на время долгого запроса к ИИ
    await session.commit()
    try:
        analysis = await ai.ask(messages)
    except AiError as error:
        await call.message.answer(str(error))
        return
    await exams_svc.save_analysis(session, doctor.id, exam.id, analysis)
    await send_plain(call.message, analysis + texts.AI_NOTE)
