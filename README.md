# Доктор Кто — Telegram-бот для ведения пациентов

Помощник врача: карточки пациентов, приёмы, заметки, напоминания о контроле и утренняя сводка.
Данные пациентов шифруются в БД, каждый врач видит только своих пациентов.

- Продукт: [PROJECT_IDEA.md](PROJECT_IDEA.md)
- Техническая спецификация: [TECH_SPEC.md](TECH_SPEC.md)

## Локальный запуск

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env      # заполнить BOT_TOKEN, ENCRYPTION_KEY, ADMIN_IDS
alembic upgrade head
python -m bot
pytest
```

## Деплой на Railway

1. New Project → Deploy from GitHub repo → `DRwho`. Добавить сервис **Redis**.
2. В сервисе бота: Settings → Networking → **Generate Domain**.
3. Variables:
   - `BOT_TOKEN` — от @BotFather
   - `DATABASE_URL` — Supabase → Project Settings → Database → Connection string → **Session pooler**
   - `ENCRYPTION_KEY` — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - `ADMIN_IDS` — ваш Telegram ID (узнать у @userinfobot)
   - `REDIS_URL` — `${{Redis.REDIS_URL}}`
4. Миграции (`alembic upgrade head`) выполняются при старте контейнера. Порт домена в Railway должен быть 8080.
   Webhook включается автоматически по `RAILWAY_PUBLIC_DOMAIN`.

Регистрация врачей — по приглашениям: администратор отправляет боту `/invite` и пересылает ссылку врачу.
