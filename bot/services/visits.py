from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Note, Visit, VisitKind
from bot.services import audit
from bot.services.patients import get_patient
from bot.utils import utcnow


VISIT_FIELDS = ("complaints", "anamnesis", "status", "diagnosis", "prescriptions", "comment")
# Поля, которые бот спрашивает по шагам; остальные можно заполнить на экране черновика
KIND_STEPS = {
    VisitKind.PRIMARY: VISIT_FIELDS,
    VisitKind.DIARY: ("complaints", "status", "prescriptions", "comment"),
}


@dataclass
class VisitInput:
    kind: str = VisitKind.PRIMARY
    complaints: str | None = None
    anamnesis: str | None = None
    status: str | None = None
    diagnosis: str | None = None
    prescriptions: str | None = None
    comment: str | None = None


async def add_visit(
    session: AsyncSession,
    doctor_id: int,
    patient_id: int,
    data: VisitInput,
    visit_at: datetime | None = None,
) -> Visit | None:
    if await get_patient(session, doctor_id, patient_id) is None:
        return None
    visit = Visit(doctor_id=doctor_id, patient_id=patient_id, visit_at=visit_at or utcnow(), **asdict(data))
    session.add(visit)
    await session.flush()
    audit.log(session, doctor_id, "create", "visit", visit.id)
    return visit


async def list_visits(
    session: AsyncSession, doctor_id: int, patient_id: int, limit: int | None = 10, kind: str | None = None
) -> list[Visit]:
    query = (
        select(Visit)
        .where(Visit.doctor_id == doctor_id, Visit.patient_id == patient_id)
        .order_by(Visit.visit_at.desc(), Visit.id.desc())
        .limit(limit)
    )
    if kind is not None:
        query = query.where(Visit.kind == kind)
    return list(await session.scalars(query))


async def add_note(session: AsyncSession, doctor_id: int, patient_id: int, text: str) -> Note | None:
    if await get_patient(session, doctor_id, patient_id) is None:
        return None
    note = Note(doctor_id=doctor_id, patient_id=patient_id, text=text)
    session.add(note)
    await session.flush()
    audit.log(session, doctor_id, "create", "note", note.id)
    return note


async def list_notes(session: AsyncSession, doctor_id: int, patient_id: int, limit: int = 10) -> list[Note]:
    rows = await session.scalars(
        select(Note)
        .where(Note.doctor_id == doctor_id, Note.patient_id == patient_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(limit)
    )
    return list(rows)
