from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import texts
from bot.config import Settings
from bot.db.models import Doctor
from bot.handlers.views import send
from bot.services import registration
from bot.states import Registration
from bot.utils import esc, parse_timezone
from bot.validators import parse_full_name, parse_short_text

router = Router(name="registration")


def _invite_required(settings: Settings, telegram_id: int) -> bool:
    return settings.registration_mode == "invite" and telegram_id not in settings.admin_id_set


@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    doctor: Doctor | None,
) -> None:
    await state.clear()
    if doctor is not None:
        await message.answer(texts.WELCOME_BACK.format(name=esc(doctor.full_name)), reply_markup=kb.main_menu())
        return
    if message.from_user is None:
        return
    code = (command.args or "").strip()
    if _invite_required(settings, message.from_user.id):
        if not code:
            await state.set_state(Registration.invite)
            await message.answer(texts.NEED_INVITE, reply_markup=ReplyKeyboardRemove())
            return
        if await registration.find_valid_invite(session, code) is None:
            await state.set_state(Registration.invite)
            await message.answer(texts.INVITE_INVALID, reply_markup=ReplyKeyboardRemove())
            return
    await _ask_consent(message, state, code or None)


async def _ask_consent(message: Message, state: FSMContext, code: str | None) -> None:
    await state.update_data(invite=code)
    await state.set_state(Registration.consent)
    await message.answer(texts.CONSENT, reply_markup=kb.consent_kb())


@router.message(Registration.invite, F.text)
async def invite_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    code = (message.text or "").strip()
    if await registration.find_valid_invite(session, code) is None:
        await message.answer(texts.INVITE_INVALID)
        return
    await _ask_consent(message, state, code)


@router.callback_query(Registration.consent, F.data == kb.CONSENT_CB)
async def consent(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Registration.full_name)
    await send(call, texts.ASK_DOCTOR_NAME, kb.input_kb())


@router.message(Registration.full_name, F.text)
async def doctor_name(message: Message, state: FSMContext) -> None:
    name = parse_full_name(message.text or "")
    if name is None:
        await message.answer(texts.BAD_NAME)
        return
    await state.update_data(full_name=name)
    await state.set_state(Registration.specialty)
    await message.answer(texts.ASK_SPECIALTY, reply_markup=kb.input_kb())


@router.message(Registration.specialty, F.text)
async def specialty(message: Message, state: FSMContext) -> None:
    value = parse_short_text(message.text or "")
    if value is None:
        await message.answer(texts.BAD_SPECIALTY)
        return
    await state.update_data(specialty=value)
    await state.set_state(Registration.timezone)
    await message.answer(texts.ASK_TIMEZONE, reply_markup=kb.timezones_kb())


@router.message(Registration.timezone, F.text)
async def timezone(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    raw = (message.text or "").strip()
    tz = texts.TIMEZONES.get(raw) or parse_timezone(raw)
    if tz is None or message.from_user is None:
        await message.answer(texts.BAD_TIMEZONE)
        return
    data = await state.get_data()
    doctor = await registration.register_doctor(
        session,
        telegram_id=message.from_user.id,
        full_name=data["full_name"],
        specialty=data["specialty"],
        timezone=tz,
        invite_code=data.get("invite"),
        require_invite=_invite_required(settings, message.from_user.id),
    )
    await state.clear()
    if doctor is None:
        await message.answer(texts.INVITE_INVALID, reply_markup=ReplyKeyboardRemove())
        return
    await message.answer(texts.REGISTERED.format(name=esc(doctor.full_name)), reply_markup=kb.main_menu())
