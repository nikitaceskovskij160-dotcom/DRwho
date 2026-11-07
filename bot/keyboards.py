from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts
from bot.db.models import ExamResult, Patient, Reminder, VisitTemplate
from bot.services.patients import PatientPage
from bot.utils import fmt_date, short_name, to_local


class PatientsPageCb(CallbackData, prefix="pl"):
    page: int
    archived: bool = False


class PatientCb(CallbackData, prefix="p"):
    # open, edit, archive, restore, visits, notes, add_visit, add_note, remind
    action: str
    id: int


class EditFieldCb(CallbackData, prefix="ef"):
    patient_id: int
    field: str


class RemindCb(CallbackData, prefix="ri"):
    patient_id: int  # 0 — напоминание без пациента
    days: int  # 0 — не напоминать, -1 — своя дата


class ReminderCb(CallbackData, prefix="r"):
    action: str
    id: int


class VisitStartCb(CallbackData, prefix="vs"):
    patient_id: int
    kind: str
    template_id: int = 0  # 0 — пустой приём


class DraftCb(CallbackData, prefix="d"):
    action: str  # edit, save
    field: str = ""


class TemplateCb(CallbackData, prefix="t"):
    action: str  # list, new, open, edit, delete
    id: int = 0


class TemplateFieldCb(CallbackData, prefix="tf"):
    id: int
    field: str


class ExamCb(CallbackData, prefix="ex"):
    action: str  # open, file, analyze
    id: int


class DocCb(CallbackData, prefix="doc"):
    patient_id: int
    kind: str  # primary, diary, history


CONSENT_CB = "consent_yes"


def _reply(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows], resize_keyboard=True
    )


def main_menu() -> ReplyKeyboardMarkup:
    return _reply(
        [
            [texts.BTN_PATIENTS, texts.BTN_ADD],
            [texts.BTN_SEARCH, texts.BTN_TODAY],
            [texts.BTN_REMINDERS, texts.BTN_TEMPLATES],
            [texts.BTN_AI, texts.BTN_HELP],
        ]
    )


def input_kb(skip: bool = False, options: list[list[str]] | None = None) -> ReplyKeyboardMarkup:
    rows = list(options or [])
    rows.append([texts.BTN_SKIP, texts.BTN_CANCEL] if skip else [texts.BTN_CANCEL])
    return _reply(rows)


def timezones_kb() -> ReplyKeyboardMarkup:
    names = list(texts.TIMEZONES)
    return input_kb(options=[names[i : i + 3] for i in range(0, len(names), 3)])


def sex_kb() -> ReplyKeyboardMarkup:
    return input_kb(skip=True, options=[[texts.BTN_MALE, texts.BTN_FEMALE]])


def consent_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.BTN_CONSENT, callback_data=CONSENT_CB)
    return builder.as_markup()


def patient_button_text(patient: Patient) -> str:
    text = short_name(patient.full_name)
    if patient.birth_date:
        text += f", {patient.birth_date.year}"
    return ("🗄 " if patient.is_archived else "") + text


def patients_list(page: PatientPage, archived: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for patient in page.items:
        builder.button(text=patient_button_text(patient), callback_data=PatientCb(action="open", id=patient.id))
    builder.adjust(1)
    nav = InlineKeyboardBuilder()
    if page.page > 0:
        nav.button(text="◀️", callback_data=PatientsPageCb(page=page.page - 1, archived=archived))
    if page.pages > 1:
        nav.button(text=f"{page.page + 1}/{page.pages}", callback_data=PatientsPageCb(page=page.page, archived=archived))
    if page.page < page.pages - 1:
        nav.button(text="▶️", callback_data=PatientsPageCb(page=page.page + 1, archived=archived))
    builder.attach(nav)
    toggle = InlineKeyboardBuilder()
    toggle.button(
        text="👥 Активные" if archived else "🗄 Архив",
        callback_data=PatientsPageCb(page=0, archived=not archived),
    )
    builder.attach(toggle)
    return builder.as_markup()


def search_results(patients: list[Patient]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for patient in patients:
        builder.button(text=patient_button_text(patient), callback_data=PatientCb(action="open", id=patient.id))
    builder.adjust(1)
    return builder.as_markup()


def patient_card(patient: Patient) -> InlineKeyboardMarkup:
    pid = patient.id
    builder = InlineKeyboardBuilder()
    builder.button(text="🩺 Приём", callback_data=PatientCb(action="add_visit", id=pid))
    builder.button(text="📝 Заметка", callback_data=PatientCb(action="add_note", id=pid))
    builder.button(text="📋 История", callback_data=PatientCb(action="visits", id=pid))
    builder.button(text="🗒 Заметки", callback_data=PatientCb(action="notes", id=pid))
    builder.button(text="🔬 Обследования", callback_data=PatientCb(action="exams", id=pid))
    builder.button(text="🖨 Документы", callback_data=PatientCb(action="docs", id=pid))
    builder.button(text=texts.BTN_AI, callback_data=PatientCb(action="ai", id=pid))
    builder.button(text="⏰ Напомнить", callback_data=PatientCb(action="remind", id=pid))
    builder.button(text="✏️ Изменить", callback_data=PatientCb(action="edit", id=pid))
    if patient.is_archived:
        builder.button(text="♻️ Восстановить", callback_data=PatientCb(action="restore", id=pid))
    else:
        builder.button(text="🗄 В архив", callback_data=PatientCb(action="archive", id=pid))
    builder.button(text="◀️ К списку", callback_data=PatientsPageCb(page=0, archived=patient.is_archived))
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def visit_start(patient_id: int, templates: list[VisitTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kind, title in texts.VISIT_KIND_TITLES.items():
        builder.button(text=f"🩺 {title}", callback_data=VisitStartCb(patient_id=patient_id, kind=kind))
    for template in templates:
        callback = VisitStartCb(patient_id=patient_id, kind=template.kind, template_id=template.id)
        builder.button(text=f"📑 {template.title}", callback_data=callback)
    builder.button(text="◀️ К карточке", callback_data=PatientCb(action="open", id=patient_id))
    builder.adjust(1)
    return builder.as_markup()


def visit_draft() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, title in texts.VISIT_FIELD_TITLES.items():
        builder.button(text=f"✏️ {title}", callback_data=DraftCb(action="edit", field=field))
    builder.button(text=texts.BTN_SAVE, callback_data=DraftCb(action="save"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def templates_list(templates: list[VisitTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for template in templates:
        builder.button(text=f"📑 {template.title}", callback_data=TemplateCb(action="open", id=template.id))
    builder.button(text="➕ Новый шаблон", callback_data=TemplateCb(action="new"))
    builder.adjust(1)
    return builder.as_markup()


def template_card(template_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить", callback_data=TemplateCb(action="edit", id=template_id))
    builder.button(text="🗑 Удалить", callback_data=TemplateCb(action="delete", id=template_id))
    builder.button(text="◀️ К шаблонам", callback_data=TemplateCb(action="list"))
    builder.adjust(2, 1)
    return builder.as_markup()


def template_fields(template_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.TEMPLATE_TITLE_FIELD, callback_data=TemplateFieldCb(id=template_id, field="title"))
    for field, title in texts.VISIT_FIELD_TITLES.items():
        builder.button(text=title, callback_data=TemplateFieldCb(id=template_id, field=field))
    builder.button(text="◀️ К шаблону", callback_data=TemplateCb(action="open", id=template_id))
    builder.adjust(1, 2, 2, 2, 1)
    return builder.as_markup()


def exams_list(patient_id: int, exams: list[ExamResult]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for exam in exams:
        label = f"{fmt_date(exam.created_at.date())} {exam.title}"
        builder.button(text=label, callback_data=ExamCb(action="open", id=exam.id))
    builder.button(text="➕ Добавить результат", callback_data=PatientCb(action="add_exam", id=patient_id))
    builder.button(text="◀️ К карточке", callback_data=PatientCb(action="open", id=patient_id))
    builder.adjust(1)
    return builder.as_markup()


def exam_card(exam: ExamResult) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 Разобрать с ИИ", callback_data=ExamCb(action="analyze", id=exam.id))
    if exam.file_id:
        builder.button(text="📎 Показать файл", callback_data=ExamCb(action="file", id=exam.id))
    builder.button(text="◀️ К обследованиям", callback_data=PatientCb(action="exams", id=exam.patient_id))
    builder.adjust(1)
    return builder.as_markup()


def documents(patient_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kind, title in (
        ("primary", texts.DOC_PRIMARY),
        ("diary", texts.DOC_DIARY),
        ("history", texts.DOC_HISTORY),
    ):
        builder.button(text=f"🖨 {title}", callback_data=DocCb(patient_id=patient_id, kind=kind))
    builder.button(text="◀️ К карточке", callback_data=PatientCb(action="open", id=patient_id))
    builder.adjust(1)
    return builder.as_markup()


def back_to_card(patient_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ К карточке", callback_data=PatientCb(action="open", id=patient_id))
    return builder.as_markup()


def edit_fields(patient_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, title in texts.FIELD_TITLES.items():
        builder.button(text=title, callback_data=EditFieldCb(patient_id=patient_id, field=field))
    builder.button(text="◀️ К карточке", callback_data=PatientCb(action="open", id=patient_id))
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def remind_options(patient_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for days, label in ((7, "Через 7 дн."), (14, "Через 14 дн."), (30, "Через 30 дн.")):
        builder.button(text=label, callback_data=RemindCb(patient_id=patient_id, days=days))
    builder.button(text="📅 Своя дата", callback_data=RemindCb(patient_id=patient_id, days=-1))
    builder.button(text="Не напоминать", callback_data=RemindCb(patient_id=patient_id, days=0))
    builder.adjust(3, 2)
    return builder.as_markup()


def reminders_list(reminders: list[Reminder], tz: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reminder in reminders:
        label = to_local(reminder.remind_at, tz).strftime("%d.%m %H:%M")
        if reminder.patient is not None:
            label += " " + short_name(reminder.patient.full_name)
        builder.button(text=f"❌ {label}", callback_data=ReminderCb(action="cancel", id=reminder.id))
    builder.button(text="➕ Новое напоминание", callback_data=RemindCb(patient_id=0, days=-1))
    builder.adjust(1)
    return builder.as_markup()
