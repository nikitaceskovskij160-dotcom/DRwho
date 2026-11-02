"""Проверка пользовательского ввода. Каждая функция возвращает значение или None при ошибке."""

from datetime import date
from typing import Any

from bot import texts
from bot.utils import only_digits, parse_date, utcnow

MAX_NAME_LEN = 150
MAX_SHORT_LEN = 100
MAX_TEXT_LEN = 3000
MIN_BIRTH_DATE = date(1900, 1, 1)


def parse_full_name(text: str) -> str | None:
    value = " ".join(text.split())
    if 2 <= len(value) <= MAX_NAME_LEN and any(ch.isalpha() for ch in value):
        return value
    return None


def parse_short_text(text: str) -> str | None:
    value = " ".join(text.split())
    return value if 0 < len(value) <= MAX_SHORT_LEN else None


def parse_long_text(text: str) -> str | None:
    value = text.strip()
    return value if 0 < len(value) <= MAX_TEXT_LEN else None


def parse_birth_date(text: str, today: date | None = None) -> date | None:
    value = parse_date(text)
    today = today or utcnow().date()
    if value is None or not MIN_BIRTH_DATE <= value <= today:
        return None
    return value


def parse_sex(text: str) -> str | None:
    return {"М": "M", "M": "M", "Ж": "F", "F": "F"}.get(text.strip().upper())


def parse_phone(text: str) -> str | None:
    digits = only_digits(text)
    if not 5 <= len(digits) <= 15:
        return None
    return ("+" if text.strip().startswith("+") else "") + digits


PATIENT_FIELD_PARSERS = {
    "full_name": (parse_full_name, texts.BAD_NAME),
    "birth_date": (parse_birth_date, texts.BAD_BIRTH_DATE),
    "sex": (parse_sex, texts.BAD_SEX),
    "phone": (parse_phone, texts.BAD_PHONE),
    "notes": (parse_long_text, texts.BAD_TEXT.format(limit=MAX_TEXT_LEN)),
}


def parse_patient_field(field: str, text: str) -> tuple[bool, Any, str]:
    """Возвращает (ok, value, error). «Пропустить» очищает необязательное поле."""
    parser, error = PATIENT_FIELD_PARSERS[field]
    if text == texts.BTN_SKIP:
        return field != "full_name", None, error
    value = parser(text)
    return value is not None, value, error
