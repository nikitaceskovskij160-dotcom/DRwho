import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Doctor, Invite, Patient
from bot.services import audit
from bot.utils import local_today, utcnow

INVITE_TTL = timedelta(days=7)


async def get_doctor(session: AsyncSession, telegram_id: int) -> Doctor | None:
    return await session.scalar(select(Doctor).where(Doctor.telegram_id == telegram_id))


async def create_invite(session: AsyncSession, created_by: int, now: datetime | None = None) -> Invite:
    now = now or utcnow()
    invite = Invite(code=secrets.token_urlsafe(8), created_by=created_by, expires_at=now + INVITE_TTL)
    session.add(invite)
    await session.flush()
    return invite


async def find_valid_invite(session: AsyncSession, code: str, now: datetime | None = None) -> Invite | None:
    now = now or utcnow()
    return await session.scalar(
        select(Invite).where(
            Invite.code == code.strip(),
            Invite.used_by_doctor_id.is_(None),
            Invite.expires_at > now,
        )
    )


async def register_doctor(
    session: AsyncSession,
    telegram_id: int,
    full_name: str,
    specialty: str,
    timezone: str,
    invite_code: str | None = None,
    require_invite: bool = False,
    now: datetime | None = None,
) -> Doctor | None:
    """Создаёт врача. Возвращает None, если требуется приглашение, а код недействителен."""
    now = now or utcnow()
    invite = await find_valid_invite(session, invite_code, now) if invite_code else None
    if require_invite and invite is None:
        return None
    doctor = Doctor(
        telegram_id=telegram_id,
        full_name=full_name,
        specialty=specialty,
        timezone=timezone,
        consent_at=now,
        # чтобы сводка не пришла сразу после регистрации в середине дня
        last_digest_date=local_today(timezone, now),
    )
    session.add(doctor)
    await session.flush()
    if invite is not None:
        invite.used_by_doctor_id = doctor.id
    audit.log(session, doctor.id, "register", "doctor", doctor.id)
    return doctor


async def stats(session: AsyncSession) -> tuple[int, int]:
    doctors = await session.scalar(select(func.count()).select_from(Doctor)) or 0
    patients = await session.scalar(select(func.count()).select_from(Patient)) or 0
    return doctors, patients
