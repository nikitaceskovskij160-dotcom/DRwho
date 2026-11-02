from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AuditLog


def log(session: AsyncSession, doctor_id: int | None, action: str, entity: str, entity_id: int | None) -> None:
    session.add(AuditLog(doctor_id=doctor_id, action=action, entity=entity, entity_id=entity_id))
