"""Печатные документы .docx: первичный осмотр, дневниковые записи, история болезни."""

from datetime import date
from io import BytesIO

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from bot import texts
from bot.db.models import Doctor, ExamResult, Patient, Visit
from bot.render import SEX_TITLES
from bot.utils import age, fmt_date, fmt_dt


def _new_document(title: str) -> DocxDocument:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    run.bold = True
    run.font.size = Pt(14)
    return document


def _labeled(document: DocxDocument, label: str, value: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.add_run(f"{label}: ").bold = True
    paragraph.add_run(value)


def _patient_block(document: DocxDocument, patient: Patient, today: date) -> None:
    _labeled(document, "Пациент", patient.full_name)
    if patient.birth_date:
        years = age(patient.birth_date, today)
        _labeled(document, "Дата рождения", f"{fmt_date(patient.birth_date)} (возраст: {years})")
    if patient.sex:
        _labeled(document, "Пол", SEX_TITLES.get(patient.sex, patient.sex))
    if patient.phone:
        _labeled(document, "Телефон", patient.phone)
    if patient.notes:
        _labeled(document, "Примечание", patient.notes)


def _visit_block(document: DocxDocument, visit: Visit) -> None:
    for field, title in texts.VISIT_FIELD_TITLES.items():
        value = getattr(visit, field)
        if value:
            _labeled(document, title, value)


def _signature(document: DocxDocument, doctor: Doctor, today: date) -> None:
    document.add_paragraph()
    document.add_paragraph(f"Врач: {doctor.full_name}, {doctor.specialty}")
    document.add_paragraph(f"Дата: {fmt_date(today)}        Подпись: ________________")


def _to_bytes(document: DocxDocument) -> bytes:
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _section_heading(document: DocxDocument, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.add_run(text).bold = True


def primary_exam(doctor: Doctor, patient: Patient, visit: Visit, today: date) -> bytes:
    document = _new_document("Первичный осмотр")
    _patient_block(document, patient, today)
    _labeled(document, "Дата осмотра", fmt_dt(visit.visit_at, doctor.timezone))
    _visit_block(document, visit)
    _signature(document, doctor, today)
    return _to_bytes(document)


def diary(doctor: Doctor, patient: Patient, visits: list[Visit], today: date) -> bytes:
    """Дневниковые записи в хронологическом порядке."""
    document = _new_document("Дневниковые записи")
    _patient_block(document, patient, today)
    for visit in sorted(visits, key=lambda v: v.visit_at):
        _section_heading(document, fmt_dt(visit.visit_at, doctor.timezone))
        _visit_block(document, visit)
    _signature(document, doctor, today)
    return _to_bytes(document)


def medical_history(
    doctor: Doctor, patient: Patient, visits: list[Visit], exams: list[ExamResult], today: date
) -> bytes:
    """История болезни: все приёмы и обследования в хронологическом порядке."""
    document = _new_document("История болезни")
    _patient_block(document, patient, today)
    for visit in sorted(visits, key=lambda v: v.visit_at):
        kind = texts.VISIT_KIND_TITLES.get(visit.kind, visit.kind)
        _section_heading(document, f"{kind}, {fmt_dt(visit.visit_at, doctor.timezone)}")
        _visit_block(document, visit)
    if exams:
        _section_heading(document, "Результаты обследований")
        for exam in sorted(exams, key=lambda e: e.created_at):
            value = exam.text or "см. приложенный файл"
            _labeled(document, f"{fmt_dt(exam.created_at, doctor.timezone)}, {exam.title}", value)
    _signature(document, doctor, today)
    return _to_bytes(document)
