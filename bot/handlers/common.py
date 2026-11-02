import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import ErrorEvent, Message, ReplyKeyboardRemove

from bot import texts
from bot.db.models import Doctor
from bot.keyboards import main_menu

logger = logging.getLogger(__name__)
router = Router(name="common")


@router.message(StateFilter("*"), Command("cancel"))
@router.message(StateFilter("*"), F.text == texts.BTN_CANCEL)
async def cancel(message: Message, state: FSMContext, doctor: Doctor | None) -> None:
    await state.clear()
    if doctor is None:
        await message.answer(texts.CANCELLED + "\n" + texts.NOT_REGISTERED, reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(texts.CANCELLED, reply_markup=main_menu())


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def help_command(message: Message, state: FSMContext, doctor: Doctor | None) -> None:
    await state.clear()
    await message.answer(texts.HELP, reply_markup=main_menu() if doctor else None)


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext, doctor: Doctor | None) -> None:
    await state.clear()
    if doctor is None:
        await message.answer(texts.NOT_REGISTERED)
    else:
        await message.answer(texts.MENU, reply_markup=main_menu())


@router.errors()
async def on_error(event: ErrorEvent) -> None:
    # Только тип ошибки и id апдейта — без содержимого сообщений (там могут быть медданные)
    logger.error(
        "Ошибка при обработке update_id=%s: %s",
        event.update.update_id,
        type(event.exception).__name__,
        exc_info=event.exception,
    )
    target = event.update.message or (event.update.callback_query and event.update.callback_query.message)
    if isinstance(target, Message):
        try:
            await target.answer(texts.ERROR)
        except Exception:  # noqa: BLE001 — сообщить об ошибке не удалось, уже залогировано
            pass
