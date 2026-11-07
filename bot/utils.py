import html
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATE_FMT = "%d.%m.%Y"
DATETIME_FMT = "%d.%m.%Y %H:%M"
MAX_MESSAGE_LEN = 4000


def utcnow() -> datetime:
    return datetime.now(UTC)


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def truncate(text: str, limit: int = MAX_MESSAGE_LEN) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def split_text(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    """Делит длинный текст на части для Telegram, стараясь резать по переносу строки."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > 0 else limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    return chunks


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def only_digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), DATE_FMT).date()
    except ValueError:
        return None


def parse_local_datetime(text: str, tz: str, default_time: time) -> datetime | None:
    """Разбирает «ДД.ММ.ГГГГ» или «ДД.ММ.ГГГГ ЧЧ:ММ» в часовом поясе врача, возвращает UTC."""
    text = " ".join(text.split())
    for fmt in (DATETIME_FMT, DATE_FMT):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == DATE_FMT:
            parsed = datetime.combine(parsed.date(), default_time)
        return parsed.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)
    return None


def parse_timezone(text: str) -> str | None:
    """Принимает IANA-имя (Europe/Berlin) или смещение (UTC+3, +3, GMT-5)."""
    value = text.strip()
    if value.upper() in ("UTC", "GMT"):
        return "UTC"
    match = re.fullmatch(r"(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::00)?", value, re.IGNORECASE)
    if match:
        hours = int(match[2])
        if hours > 14:
            return None
        if hours == 0:
            return "UTC"
        # В зонах Etc/GMT знак инвертирован: Etc/GMT-3 = UTC+3
        sign = "-" if match[1] == "+" else "+"
        return f"Etc/GMT{sign}{hours}"
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return value


def to_local(dt: datetime, tz: str) -> datetime:
    return dt.astimezone(ZoneInfo(tz))


def local_today(tz: str, now: datetime | None = None) -> date:
    return to_local(now or utcnow(), tz).date()


def day_bounds_utc(day: date, tz: str) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=ZoneInfo(tz))
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=ZoneInfo(tz))
    return start.astimezone(UTC), end.astimezone(UTC)


def fmt_date(value: date) -> str:
    return value.strftime(DATE_FMT)


def fmt_dt(dt: datetime, tz: str) -> str:
    return to_local(dt, tz).strftime(DATETIME_FMT)


def age(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def short_name(full_name: str) -> str:
    """«Иванов Иван Иванович» -> «Иванов И.И.»"""
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    return parts[0] + " " + "".join(f"{p[0].upper()}." for p in parts[1:3])
