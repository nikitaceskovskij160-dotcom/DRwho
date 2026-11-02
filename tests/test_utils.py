from datetime import UTC, date, datetime, time

from bot.utils import age, parse_local_datetime, parse_timezone, short_name
from bot.validators import parse_birth_date, parse_patient_field, parse_phone, parse_sex


def test_parse_timezone() -> None:
    assert parse_timezone("Europe/Berlin") == "Europe/Berlin"
    assert parse_timezone("UTC+3") == "Etc/GMT-3"
    assert parse_timezone("-5") == "Etc/GMT+5"
    assert parse_timezone("utc") == "UTC"
    assert parse_timezone("Mars/Olympus") is None
    assert parse_timezone("UTC+20") is None


def test_parse_local_datetime_converts_to_utc() -> None:
    result = parse_local_datetime("15.01.2027 09:30", "Europe/Berlin", time(10, 0))
    assert result == datetime(2027, 1, 15, 8, 30, tzinfo=UTC)
    result = parse_local_datetime("15.01.2027", "Europe/Berlin", time(10, 0))
    assert result == datetime(2027, 1, 15, 9, 0, tzinfo=UTC)
    assert parse_local_datetime("завтра", "UTC", time(10, 0)) is None


def test_short_name_and_age() -> None:
    assert short_name("Иванов Иван Иванович") == "Иванов И.И."
    assert short_name("Иванов") == "Иванов"
    assert age(date(1975, 3, 12), date(2026, 3, 11)) == 50
    assert age(date(1975, 3, 12), date(2026, 3, 12)) == 51


def test_validators() -> None:
    assert parse_birth_date("12.03.1975") == date(1975, 3, 12)
    assert parse_birth_date("12.03.3000") is None
    assert parse_birth_date("1975-03-12") is None
    assert parse_phone("+7 (999) 123-45-67") == "+79991234567"
    assert parse_phone("12") is None
    assert parse_sex("ж") == "F"
    assert parse_sex("x") is None


def test_skip_allowed_only_for_optional_fields() -> None:
    from bot import texts

    assert parse_patient_field("phone", texts.BTN_SKIP)[:2] == (True, None)
    assert parse_patient_field("full_name", texts.BTN_SKIP)[0] is False
