"""visit kind, anamnesis, status; visit templates; exam results

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("visit_templates", "exam_results")


def _pk() -> sa.Column:
    return sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _fk(name: str, target: str) -> sa.Column:
    return sa.Column(name, sa.BigInteger(), sa.ForeignKey(target, ondelete="CASCADE"), nullable=False)


def _text(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=nullable)


def upgrade() -> None:
    with op.batch_alter_table("visits") as batch:
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="primary"))
        batch.add_column(_text("anamnesis"))
        batch.add_column(_text("status"))

    op.create_table(
        "visit_templates",
        _pk(),
        _fk("doctor_id", "doctors.id"),
        _text("title", nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        _text("complaints"),
        _text("anamnesis"),
        _text("status"),
        _text("diagnosis"),
        _text("prescriptions"),
        _text("comment"),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_visit_templates_doctor_id", "visit_templates", ["doctor_id"])
    op.create_table(
        "exam_results",
        _pk(),
        _fk("doctor_id", "doctors.id"),
        _fk("patient_id", "patients.id"),
        _text("title", nullable=False),
        _text("text"),
        _text("file_id"),
        sa.Column("file_mime", sa.String(32), nullable=True),
        _text("analysis"),
        _ts("created_at"),
    )
    op.create_index("ix_exam_results_patient_id", "exam_results", ["patient_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    with op.batch_alter_table("visits") as batch:
        batch.drop_column("status")
        batch.drop_column("anamnesis")
        batch.drop_column("kind")
