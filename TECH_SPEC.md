# TECH_SPEC — техническая спецификация «Доктор Кто»

> Версия 1.0 (2026-11-02). Продуктовое описание — в [PROJECT_IDEA.md](PROJECT_IDEA.md).
> Этот документ — «как строим». Любое отступление от него согласуется и фиксируется здесь.

---

## 1. Инфраструктура

```
 GitHub (nikitaceskovskij160-dotcom/DRwho)
   │  push в main → GitHub Actions (lint + tests) → Railway auto-deploy
   ▼
 Railway project "drwho"
   ├── service: bot      (Python 3.12, Dockerfile, aiohttp-сервер на $PORT)
   │      ├─ POST /webhook/<path>  ← Telegram Bot API
   │      └─ GET  /health          ← healthcheck Railway
   └── service: redis    (Railway Redis, FSM-хранилище, private network)
   │
   ▼  (asyncpg, TLS, Session Pooler :5432)
 Supabase project ocfqhwgrcttrjynuktff → PostgreSQL (только как БД)
```

| Компонент | Решение | Почему |
|---|---|---|
| Хостинг | Railway, 1 сервис `bot`, **1 реплика** | Простой деплой из GitHub; одна реплика нужна для планировщика |
| Режим бота | **Webhook** в prod, long polling локально | Нет конфликта `getUpdates` при перекрытии старого и нового контейнера во время деплоя |
| БД | Supabase PostgreSQL через SQLAlchemy + asyncpg | Управляемый Postgres, бэкапы, веб-консоль |
| FSM | Railway Redis | Состояние диалогов переживает редеплой |
| Миграции | Alembic, запуск в Railway **Pre-Deploy Command** | Схема обновляется до старта нового кода |
| CI | GitHub Actions | Railway включает «Wait for CI» — деплой только при зелёных тестах |

### 1.1 Supabase: как используем
- Бот подключается **напрямую к Postgres** (строка подключения), а не через Supabase REST/JS-клиент.
  Ключи `anon` и `service_role` боту **не нужны**.
- Строка подключения: Supabase → Project Settings → Database → Connection string →
  **Session pooler** (IPv4, порт 5432):
  `postgresql+asyncpg://postgres.ocfqhwgrcttrjynuktff:<DB_PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres`
  (Direct connection у Supabase — только IPv6; Transaction pooler :6543 несовместим с prepared statements asyncpg.)
- **RLS включён на всех таблицах без политик** → через публичный Data API с `anon`-ключом данные
  недоступны. Бот ходит ролью `postgres`, которая RLS обходит. Включение RLS — часть каждой миграции, создающей таблицу.
- `service_role` ключ нигде в коде не используется и не хранится в репозитории.
- Бэкапы: на Free-плане Supabase нет PITR → ежедневный `pg_dump` (GitHub Actions по cron, зашифрованный артефакт) [?].

### 1.2 Правовые требования
Владелец проекта не из РФ, требования 152-ФЗ о локализации не применяются. Медданные всё равно
считаются особо чувствительными почти в любой юрисдикции (например, GDPR ст. 9 в ЕС), поэтому сохраняем:
шифрование полей, изоляцию данных врачей, согласие при регистрации, отсутствие ПДн в логах.
Перед пилотом уточнить законы страны, где работают врачи, и выбрать регион Supabase поблизости.

---

## 2. Стек и зависимости

| Пакет | Назначение |
|---|---|
| `aiogram==3.*` | Telegram-фреймворк (Router, FSM, CallbackData, webhook для aiohttp) |
| `aiohttp` | Веб-сервер для webhook и `/health` |
| `sqlalchemy[asyncio]==2.*`, `asyncpg` | ORM и драйвер |
| `alembic` | Миграции |
| `redis` | FSM storage (`aiogram.fsm.storage.redis.RedisStorage`) |
| `apscheduler==3.*` | Периодические задачи (тик напоминаний, утренняя сводка) |
| `pydantic-settings` | Конфигурация из env |
| `cryptography` | Fernet-шифрование полей, HMAC для поисковых индексов |
| `structlog` или `logging` | JSON-логи в stdout (Railway собирает) |
| dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `aiosqlite` | Тесты и качество |

Версии фиксируются в `requirements.txt` (prod) и `requirements-dev.txt`.

---

## 3. Конфигурация (переменные окружения)

| Переменная | Где | Пример / описание |
|---|---|---|
| `BOT_TOKEN` | Railway, `.env` | Токен от @BotFather (отдельный бот для dev и prod) |
| `BOT_MODE` | опц. | `auto` (по умолчанию): webhook, если есть `RAILWAY_PUBLIC_DOMAIN`, иначе polling |
| `WEBHOOK_BASE_URL` | опц. | Нужен только вне Railway |
| `WEBHOOK_SECRET` | опц. | Заголовок `X-Telegram-Bot-Api-Secret-Token`; по умолчанию выводится из `BOT_TOKEN` |
| `PORT` | Railway (выдаёт сам) | Порт aiohttp |
| `DATABASE_URL` | Railway, `.env` | Строка Session pooler Supabase (см. 1.1); локально — SQLite или Docker Postgres |
| `REDIS_URL` | Railway | `${{Redis.REDIS_URL}}`; пусто → MemoryStorage |
| `ENCRYPTION_KEY` | Railway, `.env` | Fernet-ключ (`Fernet.generate_key()`); **потеря = потеря данных** |
| `ADMIN_IDS` | Railway, `.env` | Telegram ID администраторов через запятую |
| `REGISTRATION_MODE` | Railway | `invite` (по коду от админа) / `open` |
| `LOG_LEVEL` | опц. | `INFO` |
| `SENTRY_DSN` | опц. [?] | Мониторинг ошибок (без ПДн в событиях) |

Секреты хранятся **только** в Railway Variables и в локальных `.env` / `secrets.local.env` (оба в `.gitignore`).
`secrets.local.env` — доступы проекта (GitHub, Supabase), которые передал владелец.
В репозитории — `.env.example` с пустыми значениями. GitHub Secrets — только то, что нужно CI.

---

## 4. Структура кода

```
bot/
  __main__.py            # сборка Bot/Dispatcher, выбор polling|webhook, запуск scheduler
  config.py              # Settings(BaseSettings)
  web.py                 # aiohttp: /health всегда, /webhook в режиме webhook
  db/
    models.py            # Base, Doctor, Invite, Patient, Visit, Note, Reminder, AuditLog
    session.py           # engine (нормализация URL Supabase), async_sessionmaker
    types.py             # EncryptedString, EncryptedDate, UTCDateTime
  services/              # бизнес-логика + запросы к БД; всегда принимает doctor_id
    registration.py  patients.py  visits.py (приёмы и заметки)  reminders.py (и сводка)  audit.py
  security/crypto.py     # Fernet / MultiFernet
  handlers/
    __init__.py          # порядок роутеров
    common.py            # отмена, /help, /menu, глобальный error handler
    registration.py  admin.py  patients.py  visits.py  notes.py  reminders.py
    views.py             # общие экраны (карточка), show()/send()
    fallback.py          # последний роутер: непонятные сообщения
  keyboards.py           # reply/inline клавиатуры, CallbackData-фабрики
  states.py              # StatesGroup по сценариям
  middlewares.py         # DbSessionMiddleware, AuthMiddleware
  filters.py             # IsDoctor, IsAdmin
  scheduler.py           # tick_reminders(), send_digests()
  render.py              # форматирование сообщений (HTML, экранирование)
  validators.py          # проверка ввода
  texts.py               # все строки интерфейса
  utils.py               # даты, часовые пояса, нормализация
migrations/              # Alembic (env.py async), versions/0001_initial.py
tests/                   # pytest на in-memory SQLite + тест миграций
Dockerfile  railway.json  .github/workflows/ci.yml
requirements.txt  requirements-dev.txt  pyproject.toml
```
Отдельного слоя репозиториев нет: в MVP запросы живут в сервисах, изоляция — фильтр `doctor_id` в каждом запросе.

### Поток обработки апдейта
`Telegram → /webhook → Dispatcher → ThrottlingMW → DbSessionMW → AuthMW → Router(handler)
→ Service(session, doctor) → Repository → БД → ответ handler'а`

Правила слоёв:
- Handler не делает запросов к БД сам — только через сервисы.
- Сервис не импортирует aiogram. Принимает `AsyncSession` и `doctor_id`, возвращает модели.
- Каждый запрос к данным пациентов **обязательно** фильтруется по `doctor_id` — главная защита изоляции.

---

## 5. Модель данных

Все `id` — `BIGINT IDENTITY`; все времена — `TIMESTAMPTZ` в UTC. `🔒` — шифруется Fernet (`EncryptedString`, в БД `TEXT`).

**doctors**: `id`, `telegram_id BIGINT UNIQUE NOT NULL`, `full_name 🔒`, `specialty VARCHAR(100)`,
`timezone VARCHAR(64) DEFAULT 'Europe/Moscow'`, `digest_time TIME DEFAULT '08:00'`, `last_digest_date DATE NULL`,
`consent_at TIMESTAMPTZ NOT NULL`, `is_active BOOL DEFAULT true`, `created_at`, `updated_at`.

**invites**: `id`, `code VARCHAR(16) UNIQUE`, `created_by` (telegram_id админа), `used_by_doctor_id NULL`, `expires_at`, `created_at`.

**patients**: `id`, `doctor_id FK → doctors ON DELETE CASCADE`, `full_name 🔒`, `birth_date 🔒`,
`sex VARCHAR(1) NULL` (M/F), `phone 🔒 NULL`, `notes 🔒 NULL`, `is_archived BOOL`, `created_at`, `updated_at`.
Индекс: `(doctor_id, is_archived)`.

**visits**: `id`, `doctor_id FK`, `patient_id FK ON DELETE CASCADE`, `visit_at TIMESTAMPTZ`,
`complaints 🔒`, `diagnosis 🔒`, `icd10_code VARCHAR(10) NULL`, `prescriptions 🔒`, `comment 🔒`, `created_at`, `updated_at`.
Индекс: `(patient_id, visit_at DESC)`.

**notes**: `id`, `doctor_id FK`, `patient_id FK ON DELETE CASCADE`, `text 🔒`, `created_at`.

**reminders**: `id`, `doctor_id FK`, `patient_id FK NULL`, `remind_at TIMESTAMPTZ`, `text 🔒`,
`status ENUM(pending, sent, cancelled, failed)`, `attempts SMALLINT DEFAULT 0`, `sent_at NULL`, `created_at`.
Индекс: частичный `(remind_at) WHERE status = 'pending'`.

**audit_log**: `id`, `doctor_id`, `action VARCHAR(32)` (create/update/archive/view/export/delete),
`entity VARCHAR(32)`, `entity_id BIGINT`, `created_at`. Без содержимого данных.

Поиск и сортировка (MVP): пациенты одного врача загружаются, расшифровываются и фильтруются в памяти
по подстроке ФИО (lower, ё→е) или цифрам телефона. Подходит до ~2000 пациентов на врача; при росте —
blind index (HMAC токенов ФИО) в отдельной таблице.

---

## 6. Ключевые технические решения

### 6.1 Webhook / polling
- `BOT_MODE=webhook`: на старте `bot.set_webhook(url, secret_token=WEBHOOK_SECRET, drop_pending_updates=False,
  allowed_updates=dp.resolve_used_update_types())`; aiohttp `SimpleRequestHandler` на `/webhook`.
- `BOT_MODE=polling`: `dp.start_polling()` — для локальной разработки с dev-токеном.
- `/health` отвечает 200, если есть соединение с БД (`SELECT 1`).

### 6.2 Напоминания и сводки
- Источник правды — таблица `reminders`. APScheduler только «тикает».
- `tick_reminders` каждые 60 с: `SELECT ... WHERE status='pending' AND remind_at <= now() FOR UPDATE SKIP LOCKED LIMIT 100`
  → отправка → `sent`; при ошибке `attempts += 1`, после 3 — `failed`; если бот заблокирован врачом — `failed`.
- `send_digests` каждые 5 мин: врачи, у которых в их часовом поясе наступило `digest_time` (08:00)
  и сводка сегодня ещё не отправлена (`doctors.last_digest_date`). Пустая сводка не отправляется.
- Быстрые напоминания («через 7/14/30 дней») ставятся на 10:00 по времени врача.
- Перезапуск безопасен: пропущенные за время простоя напоминания отправятся на следующем тике.

### 6.3 FSM-диалоги
- `RedisStorage` с префиксом `drwho:fsm`, TTL состояний 24 ч. Без `REDIS_URL` — `MemoryStorage`.
- Каждый шаг: кнопка «❌ Отмена» и «⏭ Пропустить» для необязательных полей.
- В FSM-данных не храним больше необходимого; после завершения — `state.clear()`.

### 6.4 Шифрование
- `EncryptedString(TypeDecorator)`: encrypt при записи, decrypt при чтении; `None` пропускается.
- Ротация ключа: `MultiFernet([new, old])` + фоновый скрипт перешифрования [этап 5].
- Ключи только из env; при отсутствии `ENCRYPTION_KEY` приложение не стартует.

### 6.5 Логи и ошибки
- JSON-логи в stdout: `update_id`, `doctor_id`, `handler`, `duration_ms`, `error_type`. **Никаких текстов сообщений и полей пациентов.**
- Глобальный error handler: пользователю — «Что-то пошло не так, попробуйте ещё раз», в лог — traceback без локальных переменных.

### 6.6 Интерфейс
- Reply-клавиатура главного меню: «👥 Пациенты», «➕ Новый пациент», «🔍 Поиск», «📅 Сегодня», «⚙️ Настройки».
- Списки — inline-кнопки, по 10 на страницу, навигация ◀️ ▶️ через `CallbackData`.
- Карточка пациента редактирует одно сообщение (`edit_message_text`), а не плодит новые.
- Parse mode — HTML, весь пользовательский ввод экранируется (`html.escape`).
- Ограничения ввода: ФИО ≤ 150, текстовые поля ≤ 3000 символов; даты `ДД.ММ.ГГГГ`.

---

## 7. Deploy и CI/CD

**Ветки**: `main` → prod (Railway). Работа в `feature/*`, слияние через PR. Dev-бот запускается локально.

**GitHub Actions `ci.yml`** (push и PR): установка зависимостей → `ruff check` → `pytest`
(`ruff format --check` и `mypy` — добавить в CI после первого прогона форматтера).

**Railway**:
- Источник: GitHub repo `DRwho`, ветка `main`, «Wait for CI» включено.
- Build: `Dockerfile` (python:3.12-slim, non-root user, `pip install --no-cache-dir -r requirements.txt`).
- Pre-deploy: `alembic upgrade head`. Start: `python -m bot`. Healthcheck: `/health`.
- Public networking: сгенерированный домен `*.up.railway.app` для webhook.
- Replicas: 1. Restart policy: on failure.

**Миграции**: только аддитивные изменения в одном релизе; удаление колонок — отдельным релизом после того, как код перестал их использовать.

---

## 8. Тестирование
- Unit: сервисы на in-memory SQLite (`aiosqlite`), ключи шифрования — тестовые.
- Обязательные тесты изоляции: врач A не может прочитать/изменить пациента врача B ни одним сервисом.
- Handlers: тесты на ключевые FSM-сценарии с моками `Bot`.
- Интеграционные (опц.): Postgres в Docker/testcontainers для проверки миграций.
- Только вымышленные данные (фабрики с Faker `ru_RU`).

---

## 9. План разработки (итерации)

| # | Итерация | Готово, когда |
|---|---|---|
| 1 | **Каркас**: репозиторий, pyproject, config, Dockerfile, railway.json, CI, `/start` эхо, `/health`, polling+webhook | Бот отвечает в Telegram из Railway, CI зелёный |
| 2 | **БД**: модели, Alembic, RLS, сессии, EncryptedString, middlewares db/auth | `alembic upgrade head` проходит на Supabase |
| 3 | **Регистрация врача**: инвайты, согласие, timezone, админ-команда `/invite` | Врач регистрируется по коду |
| 4 | **Пациенты**: добавление, список, карточка, поиск, редактирование, архив | Полный CRUD + тесты изоляции |
| 5 | **Приёмы и заметки** | История пациента в карточке |
| 6 | **Напоминания + сводка** | Напоминание приходит после редеплоя |
| 7 | **Полировка MVP**: тексты, ошибки, throttling, аудит, бэкапы | Готов пилот с реальными врачами |

Статус (2026-11-02): код итераций 1–6 написан и залит в GitHub; ждёт `BOT_TOKEN`, `DATABASE_URL` и настройки Railway.

---

## 10. Доступы и секреты (чек-лист)
- [ ] GitHub: репозиторий `DRwho` подключён к Railway (GitHub App Railway). Токен для локального пуша — через Git Credential Manager, **не** в URL remote и не в файлах.
- [ ] Telegram: два бота у @BotFather — `prod` и `dev`.
- [ ] Supabase: пароль БД и строка Session pooler → `DATABASE_URL` в Railway Variables.
- [ ] Railway: сервис Redis, переменные из раздела 3, сгенерирован домен.
- [ ] `ENCRYPTION_KEY` сгенерирован и сохранён в менеджере паролей (потеря ключа = потеря данных).
- [ ] Ключи, попавшие в переписку/чат, перевыпущены.
