from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from bot.db.models import Base

ROOT = Path(__file__).resolve().parents[1]


def test_migrations_create_all_model_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    inspector = sa.inspect(sa.create_engine(f"sqlite:///{db_path.as_posix()}"))
    tables = set(inspector.get_table_names())
    assert set(Base.metadata.tables) <= tables
    for name, table in Base.metadata.tables.items():
        db_columns = {c["name"] for c in inspector.get_columns(name)}
        assert {c.name for c in table.columns} == db_columns, name
