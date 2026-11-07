from aiogram import Router

from bot.handlers import (
    admin,
    ai,
    common,
    documents,
    exams,
    fallback,
    notes,
    patients,
    registration,
    reminders,
    templates,
    visits,
)


def setup_routers() -> Router:
    root = Router(name="root")
    # порядок важен: fallback должен быть последним
    root.include_routers(
        common.router,
        registration.router,
        admin.router,
        patients.router,
        visits.router,
        notes.router,
        reminders.router,
        templates.router,
        exams.router,
        documents.router,
        ai.router,
        fallback.router,
    )
    return root
