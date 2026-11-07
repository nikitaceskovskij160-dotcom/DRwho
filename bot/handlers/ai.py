from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import patient_context, send, send_plain
from bot.keyboards import PatientCb
from bot.services import patients as patients_svc
from bot.services.ai import AiClient, AiError, build_messages
from bot.states import AskAi
from bot.utils import esc, short_name
from bot.validators import MAX_TEXT_LEN, parse_long_text

router = Router(name="ai")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())

MAX_HISTORY_TURNS = 6


@router.message(Command("ai"))
@router.message(F.text == texts.BTN_AI)
async def ai_general(message: Message, state: FSMContext, ai: AiClient | None = None) -> None:
    await state.clear()
    if ai is None:
        await message.answer(texts.AI_DISABLED)
        return
    await state.set_state(AskAi.question)
    await state.update_data(patient_id=None, history=[])
    await message.answer(texts.AI_ASK_GENERAL, reply_markup=kb.input_kb())


@router.callback_query(PatientCb.filter(F.action == "ai"))
async def ai_patient(
    call: CallbackQuery,
    callback_data: PatientCb,
    state: FSMContext,
    session: AsyncSession,
    doctor: Doctor,
    ai: AiClient | None = None,
) -> None:
    if ai is None:
        await call.answer(texts.AI_DISABLED, show_alert=True)
        return
    patient = await patients_svc.get_patient(session, doctor.id, callback_data.id)
    if patient is None:
        await call.answer(texts.PATIENT_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(AskAi.question)
    await state.update_data(patient_id=patient.id, history=[])
    await send(call, texts.AI_ASK_PATIENT.format(name=esc(short_name(patient.full_name))), kb.input_kb())


@router.message(AskAi.question, F.text)
async def ai_question(
    message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor, ai: AiClient | None = None
) -> None:
    question = parse_long_text(message.text or "")
    if question is None:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    if ai is None:
        await state.clear()
        await message.answer(texts.AI_DISABLED, reply_markup=kb.main_menu())
        return
    data = await state.get_data()
    context = None
    if data.get("patient_id") is not None:
        patient = await patients_svc.get_patient(session, doctor.id, data["patient_id"])
        if patient is None:
            await state.clear()
            await message.answer(texts.PATIENT_NOT_FOUND, reply_markup=kb.main_menu())
            return
        context = await patient_context(session, doctor, patient)

    history = [tuple(turn) for turn in data.get("history", [])]
    await message.answer(texts.AI_THINKING)
    # отпускаем соединение с БД на время долгого запроса к ИИ
    await session.commit()
    try:
        answer = await ai.ask(build_messages(context, history, question))
    except AiError as error:
        await message.answer(str(error))
        return
    await state.update_data(history=[*history, (question, answer)][-MAX_HISTORY_TURNS:])
    await send_plain(message, answer + texts.AI_FOOTER)
