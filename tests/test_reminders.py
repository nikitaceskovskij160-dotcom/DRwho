from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Doctor, ReminderStatus
from bot.services import reminders as svc
from bot.services.patients import PatientInput, create_patient
from bot.services.registration import create_invite, find_valid_invite, register_doctor

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


async def test_due_reminders_and_mark_sent(session: AsyncSession, doctor: Doctor) -> None:
    patient = await create_patient(session, doctor.id, PatientInput(full_name="Сидоров Сидор"))
    past = await svc.create_reminder(session, doctor.id, NOW - timedelta(minutes=1), "Контроль", patient.id)
    await svc.create_reminder(session, doctor.id, NOW + timedelta(days=1), "Позже")
    await session.commit()

    due = await svc.due_reminders(session, NOW)
    assert [r.id for r in due] == [past.id]
    assert due[0].doctor.telegram_id == doctor.telegram_id
    assert due[0].patient is not None and due[0].patient.full_name == "Сидоров Сидор"

    svc.mark_sent(due[0], NOW)
    await session.commit()
    assert await svc.due_reminders(session, NOW) == []


async def test_failed_attempts_limit(session: AsyncSession, doctor: Doctor) -> None:
    reminder = await svc.create_reminder(session, doctor.id, NOW, "X")
    assert reminder is not None
    for _ in range(svc.MAX_ATTEMPTS):
        svc.mark_failed_attempt(reminder)
    assert reminder.status == ReminderStatus.FAILED


async def test_cancel_only_own_reminder(session: AsyncSession, doctor: Doctor, other_doctor: Doctor) -> None:
    reminder = await svc.create_reminder(session, doctor.id, NOW, "X")
    assert reminder is not None
    assert await svc.cancel_reminder(session, other_doctor.id, reminder.id) is False
    assert await svc.cancel_reminder(session, doctor.id, reminder.id) is True
    assert await svc.list_pending(session, doctor.id) == []


async def test_reminder_for_foreign_patient_rejected(
    session: AsyncSession, doctor: Doctor, other_doctor: Doctor
) -> None:
    patient = await create_patient(session, doctor.id, PatientInput(full_name="Чужой Пациент"))
    assert await svc.create_reminder(session, other_doctor.id, NOW, "X", patient.id) is None


def test_remind_at_in_days_uses_local_time() -> None:
    # 2 ноября 2026, 12:00 UTC = 13:00 в Берлине; +7 дней, 10:00 по Берлину = 09:00 UTC
    assert svc.remind_at_in_days("Europe/Berlin", 7, NOW) == datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


async def test_digest_due_once_per_day(session: AsyncSession, doctor: Doctor) -> None:
    doctor.last_digest_date = None
    doctor.digest_time = time(8, 0)
    morning = datetime(2026, 11, 3, 6, 59, tzinfo=UTC)  # 07:59 в Берлине
    assert await svc.doctors_due_for_digest(session, morning) == []
    after = datetime(2026, 11, 3, 7, 5, tzinfo=UTC)  # 08:05 в Берлине
    assert await svc.doctors_due_for_digest(session, after) == [doctor]
    doctor.last_digest_date = after.date()
    assert await svc.doctors_due_for_digest(session, after) == []


async def test_reminders_for_day(session: AsyncSession, doctor: Doctor) -> None:
    today = await svc.create_reminder(session, doctor.id, NOW + timedelta(hours=2), "Сегодня")
    await svc.create_reminder(session, doctor.id, NOW + timedelta(days=1), "Завтра")
    assert [r.id for r in await svc.reminders_for_day(session, doctor, NOW)] == [today.id if today else -1]


async def test_invite_flow(session: AsyncSession) -> None:
    invite = await create_invite(session, created_by=1, now=NOW)
    assert await register_doctor(session, 2001, "Без Кода", "ЛОР", "UTC", require_invite=True, now=NOW) is None
    doctor = await register_doctor(
        session, 2002, "С Кодом", "ЛОР", "UTC", invite_code=invite.code, require_invite=True, now=NOW
    )
    assert doctor is not None
    assert await find_valid_invite(session, invite.code, NOW) is None
    expired = await create_invite(session, created_by=1, now=NOW - timedelta(days=30))
    assert await find_valid_invite(session, expired.code, NOW) is None
