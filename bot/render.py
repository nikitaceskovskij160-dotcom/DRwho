"""Форматирование сообщений (HTML). Весь пользовательский текст экранируется через esc()."""

from bot import texts
from bot.db.models import Note, Patient, Reminder, Visit
from bot.services.patients import PatientPage
from bot.utils import age, esc, fmt_date, fmt_dt, local_today, short_name, to_local, truncate

SEX_TITLES = {"M": "М", "F": "Ж"}


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
        lines.append(f"\n<b>{fmt_dt(visit.visit_at, tz)}</b>")
        for title, value in (
            ("Жалобы", visit.complaints),
            ("Диагноз", visit.diagnosis),
            ("Назначения", visit.prescriptions),
            ("Комментарий", visit.comment),
        ):
            if value:
                lines.append(f"<i>{title}:</i> {esc(value)}")
    return truncate("\n".join(lines))


def notes_list(patient: Patient, notes: list[Note], tz: str) -> str:
    lines = [f"🗒 <b>Заметки: {esc(short_name(patient.full_name))}</b>"]
    if not notes:
        lines.append(texts.NO_NOTES)
    for note in notes:
        lines.append(f"\n<b>{fmt_dt(note.created_at, tz)}</b>\n{esc(note.text)}")
    return truncate("\n".join(lines))


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
