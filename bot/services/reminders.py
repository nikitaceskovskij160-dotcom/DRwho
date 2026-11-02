from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import Doctor, Reminder, ReminderStatus
from bot.services import audit
from bot.services.patients import get_patient
from bot.utils import day_bounds_utc, local_today, to_local, utcnow

DEFAULT_REMINDER_TIME = time(10, 0)
MAX_ATTEMPTS = 3


def remind_at_in_days(tz: str, days: int, now: datetime | None = None) -> datetime:
    day = local_today(tz, now) + timedelta(days=days)
    return datetime.combine(day, DEFAULT_REMINDER_TIME, tzinfo=ZoneInfo(tz)).astimezone(UTC)


async def create_reminder(
    session: AsyncSession,
    doctor_id: int,
    remind_at: datetime,
    text: str,
    patient_id: int | None = None,
) -> Reminder | None:
    if patient_id is not None and await get_patient(session, doctor_id, patient_id) is None:
        return None
    reminder = Reminder(doctor_id=doctor_id, patient_id=patient_id, remind_at=remind_at, text=text)
    session.add(reminder)
    await session.flush()
    audit.log(session, doctor_id, "create", "reminder", reminder.id)
    return reminder


async def list_pending(
    session: AsyncSession, doctor_id: int, patient_id: int | None = None, limit: int = 20
) -> list[Reminder]:
    query = (
        select(Reminder)
        .options(selectinload(Reminder.patient))
        .where(Reminder.doctor_id == doctor_id, Reminder.status == ReminderStatus.PENDING)
        .order_by(Reminder.remind_at)
        .limit(limit)
    )
    if patient_id is not None:
        query = query.where(Reminder.patient_id == patient_id)
    return list(await session.scalars(query))


async def cancel_reminder(session: AsyncSession, doctor_id: int, reminder_id: int) -> bool:
    reminder = await session.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.doctor_id == doctor_id,
            Reminder.status == ReminderStatus.PENDING,
        )
    )
    if reminder is None:
        return False
    reminder.status = ReminderStatus.CANCELLED
    audit.log(session, doctor_id, "cancel", "reminder", reminder.id)
    return True


async def due_reminders(session: AsyncSession, now: datetime, limit: int = 100) -> list[Reminder]:
    """Наступившие напоминания. FOR UPDATE SKIP LOCKED защищает от двойной отправки."""
    rows = await session.scalars(
        select(Reminder)
        .options(selectinload(Reminder.doctor), selectinload(Reminder.patient))
        .where(Reminder.status == ReminderStatus.PENDING, Reminder.remind_at <= now)
        .order_by(Reminder.remind_at)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Reminder)
    )
    return list(rows)


def mark_sent(reminder: Reminder, now: datetime) -> None:
    reminder.status = ReminderStatus.SENT
    reminder.sent_at = now


def mark_failed_attempt(reminder: Reminder, permanent: bool = False) -> None:
    reminder.attempts += 1
    if permanent or reminder.attempts >= MAX_ATTEMPTS:
        reminder.status = ReminderStatus.FAILED


async def reminders_for_day(session: AsyncSession, doctor: Doctor, now: datetime | None = None) -> list[Reminder]:
    start, end = day_bounds_utc(local_today(doctor.timezone, now), doctor.timezone)
    rows = await session.scalars(
        select(Reminder)
        .options(selectinload(Reminder.patient))
        .where(
            Reminder.doctor_id == doctor.id,
            Reminder.status == ReminderStatus.PENDING,
            Reminder.remind_at >= start,
            Reminder.remind_at < end,
        )
        .order_by(Reminder.remind_at)
    )
    return list(rows)


async def doctors_due_for_digest(session: AsyncSession, now: datetime | None = None) -> list[Doctor]:
    now = now or utcnow()
    doctors = await session.scalars(select(Doctor).where(Doctor.is_active.is_(True)))
    due = []
    for doctor in doctors:
        local = to_local(now, doctor.timezone)
        if local.time() >= doctor.digest_time and doctor.last_digest_date != local.date():
            due.append(doctor)
    return due
