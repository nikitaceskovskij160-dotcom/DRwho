from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.db.models import Doctor
from bot.keyboards import main_menu

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message, state: FSMContext, doctor: Doctor | None) -> None:
    if await state.get_state() is not None:
        await message.answer(texts.SEND_TEXT)
    elif doctor is None:
        await message.answer(texts.NOT_REGISTERED)
    else:
        await message.answer(texts.UNKNOWN, reply_markup=main_menu())


@router.callback_query()
async def unknown_callback(call: CallbackQuery, doctor: Doctor | None) -> None:
    await call.answer(texts.NOT_REGISTERED if doctor is None else texts.STALE_BUTTON, show_alert=True)
