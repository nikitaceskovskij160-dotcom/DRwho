from datetime import date
from io import BytesIO

from docx import Document
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Doctor, VisitKind
from bot.services import ai
from bot.services import documents as docs
from bot.services import exams as exams_svc
from bot.services import templates as svc
from bot.services import visits as visits_svc
from bot.services.patients import PatientInput, create_patient
from bot.services.visits import VisitInput

TODAY = date(2026, 11, 7)


def _text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)


async def test_template_belongs_to_one_doctor(session: AsyncSession, doctor: Doctor, other_doctor: Doctor) -> None:
    template = await svc.create_template(
        session, doctor.id, "Острый аппендицит", VisitKind.PRIMARY, {"complaints": "Боль в правой подвздошной области"}
    )
    assert await svc.get_template(session, other_doctor.id, template.id) is None
    assert await svc.list_templates(session, other_doctor.id) == []
    assert await svc.update_template(session, other_doctor.id, template.id, "title", "X") is None
    assert await svc.delete_template(session, other_doctor.id, template.id) is False
    assert await svc.delete_template(session, doctor.id, template.id) is True
    assert await svc.list_templates(session, doctor.id) == []


async def test_template_text_is_encrypted(session: AsyncSession, doctor: Doctor) -> None:
    await svc.create_template(session, doctor.id, "Шаблон", VisitKind.DIARY, {"status": "Живот мягкий"})
    await session.commit()
    row = (await session.execute(text("SELECT title, status FROM visit_templates"))).one()
    assert all(value.startswith("gAAAA") for value in row)


async def test_exams_isolation_and_analysis(session: AsyncSession, doctor: Doctor, other_doctor: Doctor) -> None:
    patient = await create_patient(session, doctor.id, PatientInput(full_name="Лебедев Юрий"))
    exam = await exams_svc.add_exam(session, doctor.id, patient.id, "ОАК", text="Лейкоциты 14")
    assert exam is not None
    assert await exams_svc.add_exam(session, other_doctor.id, patient.id, "X") is None
    assert await exams_svc.get_exam(session, other_doctor.id, exam.id) is None
    assert await exams_svc.list_exams(session, other_doctor.id, patient.id) == []
    assert await exams_svc.save_analysis(session, other_doctor.id, exam.id, "X") is None
    saved = await exams_svc.save_analysis(session, doctor.id, exam.id, "Лейкоцитоз")
    assert saved is not None and saved.analysis == "Лейкоцитоз"


async def test_visit_kind_filter_and_new_fields(session: AsyncSession, doctor: Doctor) -> None:
    patient = await create_patient(session, doctor.id, PatientInput(full_name="Лебедев Юрий"))
    await visits_svc.add_visit(session, doctor.id, patient.id, VisitInput(anamnesis="Болен 2 дня", status="Живот мягкий"))
    await visits_svc.add_visit(session, doctor.id, patient.id, VisitInput(kind=VisitKind.DIARY, status="Без динамики"))
    primary = await visits_svc.list_visits(session, doctor.id, patient.id, kind=VisitKind.PRIMARY)
    assert [v.anamnesis for v in primary] == ["Болен 2 дня"]
    assert len(await visits_svc.list_visits(session, doctor.id, patient.id, limit=None)) == 2


async def test_documents_contain_record(session: AsyncSession, doctor: Doctor) -> None:
    patient = await create_patient(
        session, doctor.id, PatientInput(full_name="Лебедев Юрий", birth_date=date(1980, 1, 1), sex="M")
    )
    visit = await visits_svc.add_visit(
        session, doctor.id, patient.id, VisitInput(anamnesis="Болен 2 дня", status="Живот мягкий", diagnosis="К35")
    )
    assert visit is not None
    exam = await exams_svc.add_exam(session, doctor.id, patient.id, "ОАК", text="Лейкоциты 14")
    assert exam is not None

    primary = _text(docs.primary_exam(doctor, patient, visit, TODAY))
    assert all(part in primary for part in ("Первичный осмотр", "Лебедев Юрий", "Анамнез", "Живот мягкий", "Подпись"))
    history = _text(docs.medical_history(doctor, patient, [visit], [exam], TODAY))
    assert "История болезни" in history and "Лейкоциты 14" in history
    assert "Дневниковые записи" in _text(docs.diary(doctor, patient, [visit], TODAY))


async def test_ai_context_has_no_identifiers(session: AsyncSession, doctor: Doctor) -> None:
    patient = await create_patient(
        session,
        doctor.id,
        PatientInput(full_name="Лебедев Юрий", birth_date=date(1980, 1, 1), sex="M", phone="+380501112233"),
    )
    visit = await visits_svc.add_visit(session, doctor.id, patient.id, VisitInput(complaints="Боль в животе"))
    assert visit is not None
    context = ai.build_context(patient, [visit], [], [], TODAY)
    assert "Боль в животе" in context and "Возраст: 46" in context
    for identifier in ("Лебедев", "Юрий", "380501112233", "01.01.1980"):
        assert identifier not in context


def test_ai_messages_keep_context_once_and_attach_file() -> None:
    messages = ai.build_messages("Выписка", [("Вопрос 1", "Ответ 1")], "Вопрос 2", ai.Attachment("application/pdf", b"x"))
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert "Выписка" in messages[0]["content"]
    assert messages[2]["content"][0]["type"] == "document"
    assert messages[2]["content"][1]["text"] == "Вопрос 2"

    first = ai.build_messages("Выписка", [], "Вопрос", ai.Attachment("image/jpeg", b"x"))
    assert first[0]["content"][0]["type"] == "image"
    assert "Выписка" in first[0]["content"][1]["text"]
