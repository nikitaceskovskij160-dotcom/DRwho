"""Результаты обследований пациента."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ExamResult
from bot.services import audit
from bot.services.patients import get_patient


async def add_exam(
    session: AsyncSession,
    doctor_id: int,
    patient_id: int,
    title: str,
    text: str | None = None,
    file_id: str | None = None,
    file_mime: str | None = None,
) -> ExamResult | None:
    if await get_patient(session, doctor_id, patient_id) is None:
        return None
    exam = ExamResult(
        doctor_id=doctor_id, patient_id=patient_id, title=title, text=text, file_id=file_id, file_mime=file_mime
    )
    session.add(exam)
    await session.flush()
    audit.log(session, doctor_id, "create", "exam", exam.id)
    return exam


async def get_exam(session: AsyncSession, doctor_id: int, exam_id: int) -> ExamResult | None:
    return await session.scalar(select(ExamResult).where(ExamResult.id == exam_id, ExamResult.doctor_id == doctor_id))


async def list_exams(
    session: AsyncSession, doctor_id: int, patient_id: int, limit: int | None = 20
) -> list[ExamResult]:
    rows = await session.scalars(
        select(ExamResult)
        .where(ExamResult.doctor_id == doctor_id, ExamResult.patient_id == patient_id)
        .order_by(ExamResult.created_at.desc(), ExamResult.id.desc())
        .limit(limit)
    )
    return list(rows)


async def save_analysis(session: AsyncSession, doctor_id: int, exam_id: int, analysis: str) -> ExamResult | None:
    exam = await get_exam(session, doctor_id, exam_id)
    if exam is None:
        return None
    exam.analysis = analysis
    await session.flush()
    audit.log(session, doctor_id, "analyze", "exam", exam.id)
    return exam
