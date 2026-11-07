from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import render, texts
from bot.db.models import Doctor
from bot.filters import IsDoctor
from bot.handlers.views import send, show
from bot.keyboards import TemplateCb, TemplateFieldCb
from bot.services import templates as templates_svc
from bot.services.templates import TEMPLATE_EDITABLE_FIELDS
from bot.services.visits import VISIT_FIELDS
from bot.states import AddTemplate, EditTemplate
from bot.validators import MAX_TEXT_LEN, parse_long_text, parse_short_text

router = Router(name="templates")
router.message.filter(IsDoctor())
router.callback_query.filter(IsDoctor())

KIND_BY_TITLE = {title: kind for kind, title in texts.VISIT_KIND_TITLES.items()}


def _list_text(has_templates: bool) -> str:
    return texts.TEMPLATES_TITLE if has_templates else texts.NO_TEMPLATES


def _field_prompt(field: str) -> str:
    return texts.TEMPLATE_FIELD_PROMPT.format(title=texts.VISIT_FIELD_TITLES[field])


@router.message(Command("templates"))
@router.message(F.text == texts.BTN_TEMPLATES)
async def templates_list(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    await state.clear()
    templates = await templates_svc.list_templates(session, doctor.id)
    await message.answer(_list_text(bool(templates)), reply_markup=kb.templates_list(templates))


@router.callback_query(TemplateCb.filter(F.action == "list"))
async def templates_list_cb(call: CallbackQuery, session: AsyncSession, doctor: Doctor) -> None:
    templates = await templates_svc.list_templates(session, doctor.id)
    await show(call, _list_text(bool(templates)), kb.templates_list(templates))


@router.callback_query(TemplateCb.filter(F.action == "open"))
async def template_open(call: CallbackQuery, callback_data: TemplateCb, session: AsyncSession, doctor: Doctor) -> None:
    template = await templates_svc.get_template(session, doctor.id, callback_data.id)
    if template is None:
        await call.answer(texts.TEMPLATE_NOT_FOUND, show_alert=True)
        return
    await show(call, render.template_card(template), kb.template_card(template.id))


@router.callback_query(TemplateCb.filter(F.action == "delete"))
async def template_delete(
    call: CallbackQuery, callback_data: TemplateCb, session: AsyncSession, doctor: Doctor
) -> None:
    await templates_svc.delete_template(session, doctor.id, callback_data.id)
    templates = await templates_svc.list_templates(session, doctor.id)
    await show(call, _list_text(bool(templates)), kb.templates_list(templates))


# ---------- создание ----------


@router.callback_query(TemplateCb.filter(F.action == "new"))
async def template_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddTemplate.title)
    await send(call, texts.ASK_TEMPLATE_TITLE, kb.input_kb())


@router.message(AddTemplate.title, F.text)
async def template_title(message: Message, state: FSMContext) -> None:
    title = parse_short_text(message.text or "")
    if title is None:
        await message.answer(texts.BAD_TEMPLATE_TITLE)
        return
    await state.update_data(title=title)
    await state.set_state(AddTemplate.kind)
    await message.answer(texts.ASK_TEMPLATE_KIND, reply_markup=kb.input_kb(options=[list(KIND_BY_TITLE)]))


@router.message(AddTemplate.kind, F.text)
async def template_kind(message: Message, state: FSMContext) -> None:
    kind = KIND_BY_TITLE.get(message.text or "")
    if kind is None:
        await message.answer(texts.BAD_TEMPLATE_KIND)
        return
    await state.update_data(kind=kind, fields={}, step=0)
    await state.set_state(AddTemplate.step)
    await message.answer(_field_prompt(VISIT_FIELDS[0]), reply_markup=kb.input_kb(skip=True))


@router.message(AddTemplate.step, F.text)
async def template_step(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    text = message.text or ""
    value = None if text == texts.BTN_SKIP else parse_long_text(text)
    if value is None and text != texts.BTN_SKIP:
        await message.answer(texts.BAD_TEXT.format(limit=MAX_TEXT_LEN))
        return
    data = await state.get_data()
    fields = {**data["fields"], VISIT_FIELDS[data["step"]]: value}
    next_step = data["step"] + 1
    if next_step < len(VISIT_FIELDS):
        await state.update_data(fields=fields, step=next_step)
        await message.answer(_field_prompt(VISIT_FIELDS[next_step]), reply_markup=kb.input_kb(skip=True))
        return
    template = await templates_svc.create_template(session, doctor.id, data["title"], data["kind"], fields)
    await state.clear()
    await message.answer(texts.TEMPLATE_SAVED, reply_markup=kb.main_menu())
    await message.answer(render.template_card(template), reply_markup=kb.template_card(template.id))


# ---------- редактирование ----------


@router.callback_query(TemplateCb.filter(F.action == "edit"))
async def template_edit(call: CallbackQuery, callback_data: TemplateCb, session: AsyncSession, doctor: Doctor) -> None:
    if await templates_svc.get_template(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.TEMPLATE_NOT_FOUND, show_alert=True)
        return
    await show(call, texts.CHOOSE_FIELD, kb.template_fields(callback_data.id))


@router.callback_query(TemplateFieldCb.filter(F.field.in_(TEMPLATE_EDITABLE_FIELDS)))
async def template_field(
    call: CallbackQuery, callback_data: TemplateFieldCb, state: FSMContext, session: AsyncSession, doctor: Doctor
) -> None:
    if await templates_svc.get_template(session, doctor.id, callback_data.id) is None:
        await call.answer(texts.TEMPLATE_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(EditTemplate.value)
    await state.update_data(template_id=callback_data.id, field=callback_data.field)
    if callback_data.field == "title":
        await send(call, texts.ASK_TEMPLATE_TITLE, kb.input_kb())
    else:
        await send(call, _field_prompt(callback_data.field), kb.input_kb(skip=True))


@router.message(EditTemplate.value, F.text)
async def template_value(message: Message, state: FSMContext, session: AsyncSession, doctor: Doctor) -> None:
    data = await state.get_data()
    text = message.text or ""
    if data["field"] == "title":
        value = parse_short_text(text)
        error = texts.BAD_TEMPLATE_TITLE
    else:
        value = None if text == texts.BTN_SKIP else parse_long_text(text)
        error = texts.BAD_TEXT.format(limit=MAX_TEXT_LEN)
    if value is None and (data["field"] == "title" or text != texts.BTN_SKIP):
        await message.answer(error)
        return
    template = await templates_svc.update_template(session, doctor.id, data["template_id"], data["field"], value)
    await state.clear()
    if template is None:
        await message.answer(texts.TEMPLATE_NOT_FOUND, reply_markup=kb.main_menu())
        return
    await message.answer(texts.TEMPLATE_UPDATED, reply_markup=kb.main_menu())
    await message.answer(render.template_card(template), reply_markup=kb.template_card(template.id))
