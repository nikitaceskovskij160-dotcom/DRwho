"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("doctors", "invites", "patients", "visits", "notes", "reminders", "audit_log")


def _pk() -> sa.Column:
    return sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _fk(name: str, target: str, nullable: bool = False, ondelete: str = "CASCADE") -> sa.Column:
    return sa.Column(name, sa.BigInteger(), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "doctors",
        _pk(),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("specialty", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("digest_time", sa.Time(), nullable=False),
        sa.Column("last_digest_date", sa.Date(), nullable=True),
        _ts("consent_at"),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "invites",
        _pk(),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        _fk("used_by_doctor_id", "doctors.id", nullable=True, ondelete="SET NULL"),
        _ts("expires_at"),
        _ts("created_at"),
    )
    op.create_table(
        "patients",
        _pk(),
        _fk("doctor_id", "doctors.id"),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("birth_date", sa.Text(), nullable=True),
        sa.Column("sex", sa.String(1), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_patients_doctor_id_is_archived", "patients", ["doctor_id", "is_archived"])
    op.create_table(
        "visits",
        _pk(),
        _fk("doctor_id", "doctors.id"),
        _fk("patient_id", "patients.id"),
        _ts("visit_at"),
        sa.Column("complaints", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("icd10_code", sa.String(10), nullable=True),
        sa.Column("prescriptions", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_visits_patient_id_visit_at", "visits", ["patient_id", "visit_at"])
    op.create_table(
        "notes",
        _pk(),
        _fk("doctor_id", "doctors.id"),
        _fk("patient_id", "patients.id"),
        sa.Column("text", sa.Text(), nullable=False),
        _ts("created_at"),
    )
    op.create_index("ix_notes_patient_id", "notes", ["patient_id"])
    op.create_table(
        "reminders",
        _pk(),
        _fk("doctor_id", "doctors.id"),
        _fk("patient_id", "patients.id", nullable=True),
        _ts("remind_at"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        _ts("sent_at", nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_reminders_status_remind_at", "reminders", ["status", "remind_at"])
    op.create_index("ix_reminders_doctor_id", "reminders", ["doctor_id"])
    op.create_table(
        "audit_log",
        _pk(),
        sa.Column("doctor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_audit_log_doctor_id", "audit_log", ["doctor_id"])

    if op.get_bind().dialect.name == "postgresql":
        # RLS без политик: публичный Data API Supabase (anon-ключ) не видит данные.
        # Бот подключается ролью postgres, которая RLS обходит.
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
