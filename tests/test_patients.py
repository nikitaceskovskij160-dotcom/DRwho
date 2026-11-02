from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Doctor
from bot.services import patients as svc
from bot.services import visits as visits_svc
from bot.services.patients import PatientInput
from bot.services.visits import VisitInput


async def test_patient_data_is_encrypted_at_rest(session: AsyncSession, doctor: Doctor) -> None:
    await svc.create_patient(
        session, doctor.id, PatientInput(full_name="Иванов Иван", birth_date=date(1975, 3, 12), phone="+79991234567")
    )
    await session.commit()
    raw = (await session.execute(text("SELECT full_name, birth_date, phone FROM patients"))).one()
    assert all(value.startswith("gAAAA") for value in raw)
    assert "Иванов" not in raw.full_name

    patient = (await svc.list_patients(session, doctor.id)).items[0]
    assert patient.full_name == "Иванов Иван"
    assert patient.birth_date == date(1975, 3, 12)


async def test_doctor_cannot_access_other_doctors_patients(
    session: AsyncSession, doctor: Doctor, other_doctor: Doctor
) -> None:
    patient = await svc.create_patient(session, doctor.id, PatientInput(full_name="Петров Пётр"))

    assert await svc.get_patient(session, other_doctor.id, patient.id) is None
    assert await svc.update_patient(session, other_doctor.id, patient.id, "full_name", "X") is None
    assert await svc.set_archived(session, other_doctor.id, patient.id, True) is None
    assert await svc.search_patients(session, other_doctor.id, "Петров") == []
    assert (await svc.list_patients(session, other_doctor.id)).total == 0
    assert await visits_svc.add_visit(session, other_doctor.id, patient.id, VisitInput(diagnosis="X")) is None
    assert await visits_svc.add_note(session, other_doctor.id, patient.id, "X") is None
    assert await visits_svc.list_visits(session, other_doctor.id, patient.id) == []


async def test_search_by_name_and_phone(session: AsyncSession, doctor: Doctor) -> None:
    await svc.create_patient(session, doctor.id, PatientInput(full_name="Семёнова Анна", phone="+380501112233"))
    await svc.create_patient(session, doctor.id, PatientInput(full_name="Козлов Олег"))

    assert [p.full_name for p in await svc.search_patients(session, doctor.id, "семенова")] == ["Семёнова Анна"]
    assert [p.full_name for p in await svc.search_patients(session, doctor.id, "1112233")] == ["Семёнова Анна"]
    assert await svc.search_patients(session, doctor.id, "  ") == []


async def test_list_pagination_and_archive(session: AsyncSession, doctor: Doctor) -> None:
    for i in range(12):
        await svc.create_patient(session, doctor.id, PatientInput(full_name=f"Пациент {i:02d}"))
    first = await svc.list_patients(session, doctor.id, page=0)
    second = await svc.list_patients(session, doctor.id, page=1)
    assert (first.total, first.pages, len(first.items), len(second.items)) == (12, 2, 10, 2)
    assert first.items[0].full_name == "Пациент 00"

    await svc.set_archived(session, doctor.id, first.items[0].id, True)
    assert (await svc.list_patients(session, doctor.id)).total == 11
    assert (await svc.list_patients(session, doctor.id, archived=True)).total == 1


async def test_visits_ordered_newest_first(session: AsyncSession, doctor: Doctor) -> None:
    patient = await svc.create_patient(session, doctor.id, PatientInput(full_name="Орлов Илья"))
    await visits_svc.add_visit(session, doctor.id, patient.id, VisitInput(diagnosis="Первый"))
    await visits_svc.add_visit(session, doctor.id, patient.id, VisitInput(diagnosis="Второй"))
    visits = await visits_svc.list_visits(session, doctor.id, patient.id)
    assert [v.diagnosis for v in visits] == ["Второй", "Первый"]
