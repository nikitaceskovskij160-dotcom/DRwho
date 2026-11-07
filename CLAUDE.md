# CLAUDE.md — памятка проекта «Доктор Кто»

Telegram-бот — персональный ассистент врача для ведения пациентов:
карточки пациентов, приёмы, назначения, заметки, напоминания о контрольных визитах.
Продукт (что строим) — [PROJECT_IDEA.md](PROJECT_IDEA.md). Техника (как строим) — [TECH_SPEC.md](TECH_SPEC.md).
Если решение противоречит этим файлам — сначала уточнить у пользователя, затем обновить файлы.

## Текущий статус
- Работает: регистрация по инвайтам, пациенты, приёмы (первичный осмотр, дневник; анамнез, статус),
  заметки, напоминания, сводка, шаблоны приёмов, обследования, печать .docx, ИИ-помощник.
- ИИ включается переменной `ANTHROPIC_API_KEY` в Railway; без неё ИИ-кнопки отвечают «не подключён».
- Бот @Kmissbot задеплоен на Railway (webhook), переменные заданы через API. Redis пока не подключён.
- `.github/workflows/ci.yml` НЕ залит: у GitHub-токена нет scope `workflow`, тесты ещё не запускались.
- Дальше: итерация 7 (throttling, бэкапы, полировка) и функции этапа 2 из PROJECT_IDEA.

## Инфраструктура
- Код: GitHub `nikitaceskovskij160-dotcom/DRwho` (публичный!), ветка `main` → автодеплой на Railway.
- Railway: сервис бота (Dockerfile, webhook по `RAILWAY_PUBLIC_DOMAIN`, 1 реплика) + Railway Redis.
- БД: Supabase Postgres (project ref `ocfqhwgrcttrjynuktff`) через Session pooler :5432.
  Ключи anon/service_role боту НЕ нужны. На всех таблицах RLS без политик (миграция 0001).
- Миграции: `alembic upgrade head` при старте контейнера (CMD в Dockerfile); railway.json Railway не читает
  (`configFile` пуст). Порт домена в Railway — 8080. CI: GitHub Actions (ruff check, pytest).
- Railway управляется через GraphQL API (`backboard.railway.com/graphql/v2`, `Authorization: Bearer`,
  workspace-токен и ID проекта/сервиса/окружения — в `secrets.local.env`). Домен: drwho-production.up.railway.app.
- На машине разработчика НЕТ git и Python. Заливка в GitHub — `scripts/push.ps1` (GitHub API).
  Тесты: портативный Python из NuGet в scratchpad (venv) + `pip install -r requirements-dev.txt`.

## Стек
- Python 3.12, **aiogram 3.x** (Router, FSM, middlewares, CallbackData), aiohttp (webhook, /health)
- SQLAlchemy 2.0 (async) + asyncpg + Alembic; локально и в тестах — SQLite (aiosqlite)
- Redis — FSM в prod (MemoryStorage без `REDIS_URL`); APScheduler — напоминания и сводки
- pydantic-settings; `cryptography` (Fernet/MultiFernet) для шифрования полей
- `anthropic` (Claude API, модель `claude-opus-5-5`), `python-docx` (печатные документы)
- pytest + pytest-asyncio; ruff

## Структура
```
bot/
  __main__.py  config.py  web.py        # запуск, настройки, /health + /webhook
  db/          # models.py, session.py, types.py (EncryptedString, EncryptedDate, UTCDateTime)
  services/    # registration, patients, visits (+заметки), reminders (+сводка), templates, exams,
               # documents (.docx), ai (Claude API), audit
  handlers/    # common, registration, admin, patients, visits, notes, reminders, templates, exams,
               # documents, ai, views, fallback
  keyboards.py states.py middlewares.py filters.py scheduler.py
  render.py    # форматирование сообщений   validators.py — проверка ввода
  texts.py     # все тексты бота            utils.py — даты, часовые пояса
migrations/    # Alembic, versions/0001_initial.py
tests/         # in-memory SQLite, тест изоляции врачей, тест миграций
scripts/push.ps1
```

## Основные сущности
- `doctors` — врач (telegram_id, ФИО, специализация, timezone, digest_time, consent_at)
- `invites` — коды приглашения (создаёт админ командой `/invite`)
- `patients` — пациент врача (ФИО, дата рождения, пол, телефон, примечание, is_archived)
- `visits` — приём: kind (primary/diary), жалобы, анамнез, статус, диагноз, назначения, комментарий
- `visit_templates` — шаблоны врача; при выборе заполняют черновик приёма, шаблон не меняется
- `exam_results` — обследования: текст и/или file_id Telegram, разбор ИИ (analysis)
- `notes` — заметки к пациенту
- `reminders` — напоминания (remind_at в UTC, status: pending/sent/cancelled/failed)
- `audit_log` — журнал действий (только id, без данных)

## Команды бота
`/start`, `/menu`, `/patients`, `/add`, `/search`, `/today`, `/reminders`, `/templates`, `/ai`, `/help`, `/cancel`;
админ: `/invite`, `/stats`.

## Архитектурные правила
- Handlers тонкие: валидация ввода → вызов сервиса → ответ. Запросы к БД — только в `services/`.
- Каждый запрос к данным пациентов фильтруется по `doctor_id` — врач видит только своих.
- Тексты бота — в `texts.py`; форматирование — в `render.py` с `esc()` для пользовательского текста.
- Callback-данные — только через `CallbackData`-фабрики в `keyboards.py`.
- Многошаговый ввод — FSM (`states.py`), «❌ Отмена» на каждом шаге. FSM-данные — только JSON-типы.
- Даты в БД — в UTC (`UTCDateTime`); пользователю — в часовом поясе врача. Ввод: ДД.ММ.ГГГГ.
- Напоминания хранятся в БД, планировщик только «тикает» — перезапуск безопасен.
- Изменение схемы — только новой миграцией Alembic (+ RLS для новых таблиц).

## Безопасность (критично: медицинские данные)
- НИКОГДА не логировать ФИО, диагнозы, телефоны и иные ПДн; в логах — только id и тип ошибки.
- Чувствительные поля — `EncryptedString`/`EncryptedDate`. Потеря `ENCRYPTION_KEY` = потеря данных.
- Секреты (`BOT_TOKEN`, `DATABASE_URL`, `ENCRYPTION_KEY`) — только в Railway Variables и `.env`.
- Доступы проекта (GitHub-токен, ключи Supabase) — в `secrets.local.env` (в `.gitignore`).
  Брать оттуда; не копировать в код, документы, коммиты. Репозиторий публичный.
- В тестах и примерах — только вымышленные данные.
- ИИ даёт врачу советы по решению владельца проекта, но только врачу и с пометкой «подсказка ИИ».
  В ИИ не передавать ФИО, телефон, дату рождения (`build_context`). Файлы уходят как есть.
- Перед долгим вызовом ИИ делать `session.commit()`, чтобы не держать соединение с БД.

## Стиль кода
- PEP 8, type hints, async/await для I/O, строка до 120 символов (ruff).
- Имена в коде — на английском; тексты бота, комментарии и докстринги — на русском.
- Новая сервисная функция — с тестом; обязательно тест изоляции, если она читает данные пациентов.

## Команды
```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head          # миграции (DATABASE_URL из .env)
python -m bot                 # запуск (локально — polling)
pytest; ruff check .
powershell -File scripts\push.ps1 -Message "описание"   # залить в GitHub без git
```

## Окружение
- Windows 11, PowerShell 5.1 (нет `&&` — используй `;`). Общение с пользователем — на русском.
- Пользователь не из РФ: требования 152-ФЗ не применяются.

## Правила работы для Claude
- Работать по этапам из TECH_SPEC §9 / PROJECT_IDEA; крупные изменения (схема БД, зависимости) — согласовать.
- После изменений — залить в GitHub и проверить статус CI.
- После завершения этапа — обновить «Текущий статус» в этом файле.
- Пункты с пометкой [?] в PROJECT_IDEA.md — допущения; при их касании уточнять.
