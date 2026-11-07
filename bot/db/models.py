import enum
from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Index, Integer, SmallInteger, String, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bot.db.types import EncryptedDate, EncryptedString, UTCDateTime
from bot.utils import utcnow

# BIGINT в Postgres; в SQLite автоинкремент работает только у INTEGER PRIMARY KEY
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class ReminderStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class VisitKind(enum.StrEnum):
    PRIMARY = "primary"
    DIARY = "diary"


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    specialty: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    digest_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(8, 0))
    last_digest_date: Mapped[date | None] = mapped_column(Date)
    consent_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    used_by_doctor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (Index("ix_patients_doctor_id_is_archived", "doctor_id", "is_archived"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(EncryptedDate())
    sex: Mapped[str | None] = mapped_column(String(1))
    phone: Mapped[str | None] = mapped_column(EncryptedString())
    notes: Mapped[str | None] = mapped_column(EncryptedString())
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (Index("ix_visits_patient_id_visit_at", "patient_id", "visit_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    visit_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=VisitKind.PRIMARY)
    complaints: Mapped[str | None] = mapped_column(EncryptedString())
    anamnesis: Mapped[str | None] = mapped_column(EncryptedString())
    status: Mapped[str | None] = mapped_column(EncryptedString())
    diagnosis: Mapped[str | None] = mapped_column(EncryptedString())
    icd10_code: Mapped[str | None] = mapped_column(String(10))
    prescriptions: Mapped[str | None] = mapped_column(EncryptedString())
    comment: Mapped[str | None] = mapped_column(EncryptedString())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_patient_id", "patient_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class VisitTemplate(Base):
    """Шаблон врача: заготовка приёма, которую правят под конкретного пациента."""

    __tablename__ = "visit_templates"
    __table_args__ = (Index("ix_visit_templates_doctor_id", "doctor_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=VisitKind.PRIMARY)
    complaints: Mapped[str | None] = mapped_column(EncryptedString())
    anamnesis: Mapped[str | None] = mapped_column(EncryptedString())
    status: Mapped[str | None] = mapped_column(EncryptedString())
    diagnosis: Mapped[str | None] = mapped_column(EncryptedString())
    prescriptions: Mapped[str | None] = mapped_column(EncryptedString())
    comment: Mapped[str | None] = mapped_column(EncryptedString())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )


class ExamResult(Base):
    """Результат обследования: текст и/или файл в Telegram, плюс разбор ИИ."""

    __tablename__ = "exam_results"
    __table_args__ = (Index("ix_exam_results_patient_id", "patient_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    text: Mapped[str | None] = mapped_column(EncryptedString())
    file_id: Mapped[str | None] = mapped_column(EncryptedString())
    file_mime: Mapped[str | None] = mapped_column(String(32))
    analysis: Mapped[str | None] = mapped_column(EncryptedString())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_status_remind_at", "status", "remind_at"),
        Index("ix_reminders_doctor_id", "doctor_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("patients.id", ondelete="CASCADE")
    )
    remind_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    text: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ReminderStatus.PENDING)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    doctor: Mapped[Doctor] = relationship(lazy="raise")
    patient: Mapped[Patient | None] = relationship(lazy="raise")


class AuditLog(Base):
    """Журнал действий. Хранит только идентификаторы, без содержимого данных."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_doctor_id", "doctor_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    doctor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
