"""Пациенты. Все функции принимают doctor_id и работают только с пациентами этого врача.

ФИО и телефон зашифрованы, поэтому сортировка и поиск выполняются в памяти
по расшифрованному списку пациентов одного врача (достаточно для объёмов MVP).
"""

import math
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Patient
from bot.services import audit
from bot.utils import normalize, only_digits

PAGE_SIZE = 10
SEARCH_LIMIT = 20
EDITABLE_FIELDS = ("full_name", "birth_date", "sex", "phone", "notes")


@dataclass
class PatientInput:
    full_name: str
    birth_date: date | None = None
    sex: str | None = None
    phone: str | None = None
    notes: str | None = None


@dataclass
class PatientPage:
    items: list[Patient]
    page: int
    pages: int
    total: int


async def create_patient(session: AsyncSession, doctor_id: int, data: PatientInput) -> Patient:
    patient = Patient(doctor_id=doctor_id, **asdict(data))
    session.add(patient)
    await session.flush()
    audit.log(session, doctor_id, "create", "patient", patient.id)
    return patient


async def get_patient(session: AsyncSession, doctor_id: int, patient_id: int) -> Patient | None:
    return await session.scalar(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )


async def _all_patients(session: AsyncSession, doctor_id: int, archived: bool | None) -> list[Patient]:
    query = select(Patient).where(Patient.doctor_id == doctor_id)
    if archived is not None:
        query = query.where(Patient.is_archived.is_(archived))
    rows = await session.scalars(query)
    return sorted(rows, key=lambda p: normalize(p.full_name))


async def list_patients(
    session: AsyncSession, doctor_id: int, page: int = 0, archived: bool = False
) -> PatientPage:
    patients = await _all_patients(session, doctor_id, archived)
    pages = max(1, math.ceil(len(patients) / PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    items = patients[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    return PatientPage(items=items, page=page, pages=pages, total=len(patients))


async def search_patients(session: AsyncSession, doctor_id: int, query: str) -> list[Patient]:
    needle = normalize(query)
    digits = only_digits(query)
    if not needle:
        return []
    found = []
    for patient in await _all_patients(session, doctor_id, archived=None):
        by_name = needle in normalize(patient.full_name)
        by_phone = len(digits) >= 4 and patient.phone is not None and digits in only_digits(patient.phone)
        if by_name or by_phone:
            found.append(patient)
    # активные пациенты выше архивных
    found.sort(key=lambda p: p.is_archived)
    return found[:SEARCH_LIMIT]


async def update_patient(
    session: AsyncSession, doctor_id: int, patient_id: int, field: str, value: object
) -> Patient | None:
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Поле {field} нельзя редактировать")
    patient = await get_patient(session, doctor_id, patient_id)
    if patient is None:
        return None
    setattr(patient, field, value)
    await session.flush()
    audit.log(session, doctor_id, "update", "patient", patient.id)
    return patient


async def set_archived(
    session: AsyncSession, doctor_id: int, patient_id: int, archived: bool
) -> Patient | None:
    patient = await get_patient(session, doctor_id, patient_id)
    if patient is None:
        return None
    patient.is_archived = archived
    await session.flush()
    audit.log(session, doctor_id, "archive" if archived else "unarchive", "patient", patient.id)
    return patient
