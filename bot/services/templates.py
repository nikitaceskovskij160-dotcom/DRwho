"""Шаблоны приёмов. Каждый шаблон принадлежит одному врачу."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import VisitTemplate
from bot.services import audit
from bot.services.visits import VISIT_FIELDS
from bot.utils import normalize

TEMPLATE_EDITABLE_FIELDS = ("title", *VISIT_FIELDS)


async def create_template(
    session: AsyncSession, doctor_id: int, title: str, kind: str, fields: dict[str, str | None]
) -> VisitTemplate:
    values = {name: fields.get(name) for name in VISIT_FIELDS}
    template = VisitTemplate(doctor_id=doctor_id, title=title, kind=kind, **values)
    session.add(template)
    await session.flush()
    audit.log(session, doctor_id, "create", "template", template.id)
    return template


async def get_template(session: AsyncSession, doctor_id: int, template_id: int) -> VisitTemplate | None:
    return await session.scalar(
        select(VisitTemplate).where(VisitTemplate.id == template_id, VisitTemplate.doctor_id == doctor_id)
    )


async def list_templates(session: AsyncSession, doctor_id: int) -> list[VisitTemplate]:
    rows = await session.scalars(select(VisitTemplate).where(VisitTemplate.doctor_id == doctor_id))
    return sorted(rows, key=lambda t: normalize(t.title))


async def update_template(
    session: AsyncSession, doctor_id: int, template_id: int, field: str, value: str | None
) -> VisitTemplate | None:
    if field not in TEMPLATE_EDITABLE_FIELDS:
        raise ValueError(f"Поле {field} нельзя редактировать")
    template = await get_template(session, doctor_id, template_id)
    if template is None:
        return None
    setattr(template, field, value)
    await session.flush()
    audit.log(session, doctor_id, "update", "template", template.id)
    return template


async def delete_template(session: AsyncSession, doctor_id: int, template_id: int) -> bool:
    template = await get_template(session, doctor_id, template_id)
    if template is None:
        return False
    await session.delete(template)
    audit.log(session, doctor_id, "delete", "template", template_id)
    return True
