"""Форматирование сообщений (HTML). Весь пользовательский текст экранируется через esc()."""

from bot import texts
from bot.db.models import ExamResult, Note, Patient, Reminder, Visit, VisitTemplate
from bot.services.patients import PatientPage
from bot.utils import MAX_MESSAGE_LEN, age, esc, fmt_date, fmt_dt, local_today, short_name, to_local, truncate

SEX_TITLES = {"M": "М", "F": "Ж"}
MAX_PREVIEW_LEN = 500
MAX_EXAM_TEXT_LEN = 1800


def patients_list(page: PatientPage, archived: bool) -> str:
    if page.total == 0:
        return texts.NO_ARCHIVED if archived else texts.NO_PATIENTS
    return (texts.ARCHIVE_TITLE if archived else texts.PATIENTS_TITLE).format(total=page.total)


def patient_card(patient: Patient, visits: list[Visit], reminders: list[Reminder], tz: str) -> str:
    lines = [f"👤 <b>{esc(patient.full_name)}</b>"]
    if patient.is_archived:
        lines.append("🗄 <i>В архиве</i>")
    if patient.birth_date:
        years = age(patient.birth_date, local_today(tz))
        lines.append(f"Дата рождения: {fmt_date(patient.birth_date)} ({years} лет)")
    if patient.sex:
        lines.append(f"Пол: {SEX_TITLES.get(patient.sex, patient.sex)}")
    if patient.phone:
        lines.append(f"Телефон: {esc(patient.phone)}")
    if patient.notes:
        lines.append(f"Примечание: {esc(patient.notes)}")
    if visits:
        lines.append("\n🩺 <b>Последние приёмы:</b>")
        for visit in visits:
            summary = visit.diagnosis or visit.complaints or "—"
            lines.append(f"• {fmt_dt(visit.visit_at, tz)[:10]} — {esc(truncate(summary, 80))}")
    if reminders:
        lines.append("\n⏰ <b>Напоминания:</b>")
        for reminder in reminders:
            lines.append(f"• {fmt_dt(reminder.remind_at, tz)} — {esc(reminder.text)}")
    return truncate("\n".join(lines))


def visits_history(patient: Patient, visits: list[Visit], tz: str) -> str:
    lines = [f"📋 <b>История приёмов: {esc(short_name(patient.full_name))}</b>"]
    if not visits:
        lines.append(texts.NO_VISITS)
    for visit in visits:
        kind = texts.VISIT_KIND_TITLES.get(visit.kind, visit.kind)
        lines.append(f"\n<b>{fmt_dt(visit.visit_at, tz)}, {kind}</b>")
        for field, title in texts.VISIT_FIELD_TITLES.items():
            value = getattr(visit, field)
            if value:
                lines.append(f"<i>{title}:</i> {esc(value)}")
    return _fit("\n".join(lines))


def _fit(text: str) -> str:
    """Обрезает HTML-текст по границе строки, чтобы не оставить незакрытый тег."""
    if len(text) <= MAX_MESSAGE_LEN:
        return text
    return text[: text.rfind("\n", 0, MAX_MESSAGE_LEN - 1)] + "\n…"


def _field_lines(fields: dict[str, str | None]) -> list[str]:
    lines = []
    for field, title in texts.VISIT_FIELD_TITLES.items():
        value = fields.get(field)
        shown = esc(truncate(value, MAX_PREVIEW_LEN)) if value else f"<i>{texts.DRAFT_EMPTY}</i>"
        lines.append(f"<b>{title}:</b> {shown}")
    return lines


def visit_draft(patient: Patient, kind: str, fields: dict[str, str | None]) -> str:
    title = texts.VISIT_KIND_TITLES.get(kind, kind)
    header = f"🩺 <b>{title}: {esc(short_name(patient.full_name))}</b>"
    return "\n".join([header, "", *_field_lines(fields), "", texts.DRAFT_HINT])


def template_card(template: VisitTemplate) -> str:
    fields = {field: getattr(template, field) for field in texts.VISIT_FIELD_TITLES}
    kind = texts.VISIT_KIND_TITLES.get(template.kind, template.kind)
    return "\n".join([f"📑 <b>{esc(template.title)}</b>", f"<i>{kind}</i>", "", *_field_lines(fields)])


def exams_list(patient: Patient, exams: list[ExamResult]) -> str:
    title = texts.EXAMS_TITLE.format(name=esc(short_name(patient.full_name)))
    return title if exams else f"{title}\n\n{texts.NO_EXAMS}"


def exam_card(exam: ExamResult, tz: str) -> str:
    lines = [f"🔬 <b>{esc(exam.title)}</b>", fmt_dt(exam.created_at, tz)]
    if exam.file_id:
        lines.append(texts.EXAM_HAS_FILE)
    if exam.text:
        lines.append(f"\n{esc(truncate(exam.text, MAX_EXAM_TEXT_LEN))}")
    if exam.analysis:
        lines.append(f"\n{texts.AI_ANALYSIS_TITLE}\n{esc(truncate(exam.analysis, MAX_EXAM_TEXT_LEN))}")
    return "\n".join(lines)


def notes_list(patient: Patient, notes: list[Note], tz: str) -> str:
    lines = [f"🗒 <b>Заметки: {esc(short_name(patient.full_name))}</b>"]
    if not notes:
        lines.append(texts.NO_NOTES)
    for note in notes:
        lines.append(f"\n<b>{fmt_dt(note.created_at, tz)}</b>\n{esc(note.text)}")
    return _fit("\n".join(lines))


def _reminder_line(reminder: Reminder, tz: str, time_only: bool = False) -> str:
    when = to_local(reminder.remind_at, tz).strftime("%H:%M" if time_only else "%d.%m.%Y %H:%M")
    who = f"{esc(short_name(reminder.patient.full_name))} — " if reminder.patient is not None else ""
    return f"• {when} {who}{esc(reminder.text)}"


def reminders_list(reminders: list[Reminder], tz: str) -> str:
    if not reminders:
        return texts.NO_REMINDERS
    return truncate("\n".join([texts.REMINDERS_TITLE, ""] + [_reminder_line(r, tz) for r in reminders]))


def day_plan(reminders: list[Reminder], tz: str, digest: bool = False) -> str:
    title = (texts.DIGEST_TITLE if digest else texts.TODAY_TITLE).format(date=fmt_date(local_today(tz)))
    if not reminders:
        return f"{title}\n\n{texts.TODAY_EMPTY}"
    return truncate("\n".join([title, ""] + [_reminder_line(r, tz, time_only=True) for r in reminders]))


def reminder_fired(reminder: Reminder) -> str:
    lines = [texts.REMINDER_FIRED]
    if reminder.patient is not None:
        lines.append(f"👤 {esc(reminder.patient.full_name)}")
    lines.append(esc(reminder.text))
    return "\n".join(lines)
