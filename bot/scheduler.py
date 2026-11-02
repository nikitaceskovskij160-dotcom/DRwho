import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import render
from bot.keyboards import PatientCb
from bot.services import reminders as reminders_svc
from bot.utils import local_today, utcnow

logger = logging.getLogger(__name__)

REMINDERS_INTERVAL_SECONDS = 60
DIGEST_INTERVAL_SECONDS = 300


async def tick_reminders(bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        now = utcnow()
        for reminder in await reminders_svc.due_reminders(session, now):
            markup = None
            if reminder.patient_id is not None:
                builder = InlineKeyboardBuilder()
                builder.button(text="👤 Открыть карточку", callback_data=PatientCb(action="open", id=reminder.patient_id))
                markup = builder.as_markup()
            try:
                await bot.send_message(reminder.doctor.telegram_id, render.reminder_fired(reminder), reply_markup=markup)
            except TelegramForbiddenError:
                # врач заблокировал бота — повторять бессмысленно
                reminders_svc.mark_failed_attempt(reminder, permanent=True)
            except TelegramAPIError as error:
                logger.warning("Не удалось отправить напоминание id=%s: %s", reminder.id, type(error).__name__)
                reminders_svc.mark_failed_attempt(reminder)
            else:
                reminders_svc.mark_sent(reminder, now)
        await session.commit()


async def send_digests(bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        now = utcnow()
        for doctor in await reminders_svc.doctors_due_for_digest(session, now):
            # отмечаем сразу, чтобы при ошибке не слать сводку каждые 5 минут
            doctor.last_digest_date = local_today(doctor.timezone, now)
            reminders = await reminders_svc.reminders_for_day(session, doctor, now)
            if not reminders:
                continue
            try:
                await bot.send_message(doctor.telegram_id, render.day_plan(reminders, doctor.timezone, digest=True))
            except TelegramAPIError as error:
                logger.warning("Не удалось отправить сводку doctor_id=%s: %s", doctor.id, type(error).__name__)
        await session.commit()


def create_scheduler(bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    job_kwargs = {"bot": bot, "session_factory": session_factory}
    scheduler.add_job(
        tick_reminders,
        "interval",
        seconds=REMINDERS_INTERVAL_SECONDS,
        kwargs=job_kwargs,
        id="reminders",
        max_instances=1,
        coalesce=True,
        next_run_time=utcnow(),
    )
    scheduler.add_job(
        send_digests,
        "interval",
        seconds=DIGEST_INTERVAL_SECONDS,
        kwargs=job_kwargs,
        id="digests",
        max_instances=1,
        coalesce=True,
        next_run_time=utcnow(),
    )
    return scheduler
