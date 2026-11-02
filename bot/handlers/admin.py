from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.filters import IsAdmin
from bot.services import registration

router = Router(name="admin")
router.message.filter(IsAdmin())


@router.message(Command("invite"))
async def create_invite(message: Message, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    invite = await registration.create_invite(session, created_by=message.from_user.id)
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={invite.code}"
    await message.answer(texts.INVITE_CREATED.format(code=invite.code, link=link))


@router.message(Command("stats"))
async def stats(message: Message, session: AsyncSession) -> None:
    doctors, patients = await registration.stats(session)
    await message.answer(texts.STATS.format(doctors=doctors, patients=patients))
