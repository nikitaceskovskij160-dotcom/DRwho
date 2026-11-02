from aiogram import Router

from bot.handlers import admin, common, fallback, notes, patients, registration, reminders, visits


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
        fallback.router,
    )
    return root
