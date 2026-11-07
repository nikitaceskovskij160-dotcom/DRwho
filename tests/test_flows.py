"""Сквозные сценарии: настоящий Dispatcher, поддельный транспорт Telegram, БД в памяти."""

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, GetMe, SendDocument, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot import keyboards as kb
from bot import texts
from bot.config import Settings
from bot.db.models import Base
from bot.handlers import setup_routers
from bot.middlewares import AuthMiddleware, DbSessionMiddleware

ADMIN_ID = 500
CHAT = Chat(id=ADMIN_ID, type="private")
USER = User(id=ADMIN_ID, is_bot=False, first_name="Врач")


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.requests.append(method)
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Bot", username="test_bot")
        if isinstance(method, AnswerCallbackQuery):
            return True
        return Message(
            message_id=len(self.requests),
            date=datetime.now(UTC),
            chat=CHAT,
            text=getattr(method, "text", None),
        )

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""


class FakeAi:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    async def ask(self, messages: list[dict[str, Any]]) -> str:
        self.calls.append(messages)
        return "Ответ ИИ"


class Chatter:
    """Шлёт боту апдейты и даёт доступ к ответам."""

    def __init__(self, dp: Dispatcher, bot: Bot, transport: FakeSession) -> None:
        self.dp, self.bot, self.transport = dp, bot, transport
        self.update_id = 0

    def _next_id(self) -> int:
        self.update_id += 1
        return self.update_id

    async def say(self, text: str) -> None:
        message = Message(message_id=self._next_id(), date=datetime.now(UTC), chat=CHAT, from_user=USER, text=text)
        await self.dp.feed_update(self.bot, Update(update_id=self.update_id, message=message))

    async def press(self, data: str) -> None:
        origin = Message(message_id=1, date=datetime.now(UTC), chat=CHAT, from_user=USER, text="x")
        call = CallbackQuery(id="1", from_user=USER, chat_instance="1", data=data, message=origin)
        await self.dp.feed_update(self.bot, Update(update_id=self._next_id(), callback_query=call))

    def replies(self) -> list[str]:
        return [m.text for m in self.transport.requests if isinstance(getattr(m, "text", None), str)]

    def last_button(self, label: str) -> str:
        """Ищет кнопку по части подписи в последних сообщениях."""
        for request in reversed(self.transport.requests):
            markup = getattr(request, "reply_markup", None)
            for row in getattr(markup, "inline_keyboard", []) or []:
                for button in row:
                    if label in button.text:
                        return button.callback_data
        raise AssertionError(f"Кнопка «{label}» не найдена")


@pytest.fixture
async def chat() -> AsyncIterator[Chatter]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = Settings(bot_token="1:test", encryption_key="x", admin_ids=str(ADMIN_ID), _env_file=None)
    dp = Dispatcher(storage=MemoryStorage(), settings=settings, ai=FakeAi())
    dp.update.outer_middleware(DbSessionMiddleware(factory))
    dp.update.outer_middleware(AuthMiddleware())
    root = setup_routers()
    dp.include_router(root)
    transport = FakeSession()
    yield Chatter(dp, Bot("1:test", session=transport), transport)
    await engine.dispose()
    # роутеры — объекты уровня модуля, а подключить роутер можно только к одному родителю
    for router in root.sub_routers:
        router._parent_router = None


async def _register(chat: Chatter) -> None:
    await chat.say("/start")
    await chat.press(kb.CONSENT_CB)
    await chat.say("Тестов Тест")
    await chat.say("Хирург")
    await chat.say("Берлин")
    assert any("Регистрация завершена" in r for r in chat.replies())


async def _add_patient(chat: Chatter) -> None:
    await chat.say(texts.BTN_ADD)
    await chat.say("Вымышленный Пётр")
    await chat.say("12.03.1975")
    await chat.say("М")
    await chat.say(texts.BTN_SKIP)
    await chat.say(texts.BTN_SKIP)
    assert texts.PATIENT_ADDED in chat.replies()


async def test_primary_visit_asks_anamnesis_and_status(chat: Chatter) -> None:
    await _register(chat)
    await _add_patient(chat)
    await chat.press(chat.last_button("Приём"))
    await chat.press(chat.last_button("Первичный осмотр"))
    for answer in ("Боль", "Болен 2 дня", "Живот мягкий", "К35", "Операция", "Без осложнений"):
        await chat.say(answer)
    replies = chat.replies()
    assert texts.VISIT_FIELD_PROMPTS["anamnesis"] in replies
    assert texts.VISIT_FIELD_PROMPTS["status"] in replies
    await chat.press(kb.DraftCb(action="save").pack())
    assert texts.VISIT_SAVED in chat.replies()

    await chat.press(chat.last_button("Через 7 дн."))
    await chat.press(chat.last_button("К карточке"))
    await chat.press(chat.last_button("История"))
    assert any("Болен 2 дня" in r and "Живот мягкий" in r for r in chat.replies())


async def test_template_is_edited_for_patient_and_stays_unchanged(chat: Chatter) -> None:
    await _register(chat)
    await chat.say(texts.BTN_TEMPLATES)
    await chat.press(chat.last_button("Новый шаблон"))
    await chat.say("Острый аппендицит")
    await chat.say(texts.VISIT_KIND_TITLES["primary"])
    await chat.say("Боль в правой подвздошной области")
    for _ in range(5):
        await chat.say(texts.BTN_SKIP)
    assert texts.TEMPLATE_SAVED in chat.replies()

    await _add_patient(chat)
    await chat.press(chat.last_button("Приём"))
    await chat.press(chat.last_button("Острый аппендицит"))
    assert any("Боль в правой подвздошной области" in r for r in chat.replies())

    await chat.press(kb.DraftCb(action="edit", field="complaints").pack())
    await chat.say("Боль справа, 6 часов")
    await chat.press(kb.DraftCb(action="save").pack())
    await chat.press(chat.last_button("Не напоминать"))
    await chat.press(chat.last_button("К карточке"))
    await chat.press(chat.last_button("История"))
    assert any("Боль справа, 6 часов" in r for r in chat.replies()[-2:])

    await chat.say(texts.BTN_TEMPLATES)
    await chat.press(chat.last_button("Острый аппендицит"))
    assert "Боль в правой подвздошной области" in chat.replies()[-1]


async def test_exam_analysis_and_document(chat: Chatter) -> None:
    await _register(chat)
    await _add_patient(chat)
    await chat.press(chat.last_button("Приём"))
    await chat.press(chat.last_button("Дневниковая запись"))
    for answer in ("Жалоб нет", "Состояние удовлетворительное", texts.BTN_SKIP, texts.BTN_SKIP):
        await chat.say(answer)
    await chat.press(kb.DraftCb(action="save").pack())
    await chat.press(chat.last_button("Не напоминать"))
    await chat.press(chat.last_button("К карточке"))

    await chat.press(chat.last_button("Обследования"))
    await chat.press(chat.last_button("Добавить результат"))
    await chat.say("ОАК")
    await chat.say("Лейкоциты 14")
    assert texts.EXAM_SAVED in chat.replies()
    await chat.press(chat.last_button("Разобрать с ИИ"))
    assert any("Ответ ИИ" in r for r in chat.replies())
    ai: FakeAi = chat.dp["ai"]
    prompt = ai.calls[0][0]["content"][0]["text"]
    assert "Лейкоциты 14" in prompt and "Вымышленный" not in prompt

    await chat.press(chat.last_button("К обследованиям"))
    await chat.press(chat.last_button("К карточке"))
    await chat.press(chat.last_button("Документы"))
    await chat.press(chat.last_button("История болезни"))
    assert any(isinstance(request, SendDocument) for request in chat.transport.requests)


async def test_ai_dialog_keeps_history(chat: Chatter) -> None:
    await _register(chat)
    await _add_patient(chat)
    await chat.press(chat.last_button("Спросить ИИ"))
    await chat.say("Что назначить?")
    await chat.say("А если аллергия?")
    ai: FakeAi = chat.dp["ai"]
    assert len(ai.calls) == 2
    assert [m["role"] for m in ai.calls[1]] == ["user", "assistant", "user"]
    assert not any("Что-то пошло не так" in r for r in chat.replies())
