from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text
from sqlmodel import SQLModel

from crodl.settings import DATABASE_URL
from crodl.tools.logger import crologger

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

#: The single column `updatecheck` used to count with. A database created then
#: has it as NOT NULL without a default, so it cannot be written to any more; see
#: `_rebuild_check_table`.
LEGACY_CHECK_COLUMN = "missing"

#: Columns tables gained after they existed. SQLite's `create_all` only ever
#: creates whole tables, so they are added here; the check table holds the
#: outcome of a check, which the next one recomputes anyway.
ADDED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "updatecheck": (
        ("available", "INTEGER NOT NULL DEFAULT 0"),
        ("upcoming", "INTEGER NOT NULL DEFAULT 0"),
        ("expired", "INTEGER NOT NULL DEFAULT 0"),
    ),
    # A work's genre, which is edited by hand and written into its parts' tags.
    "show": (("genre", "VARCHAR"),),
    "series": (("genre", "VARCHAR"),),
}


async def _add_missing_columns(connection: AsyncConnection) -> None:
    """Adds the columns older tables do not have yet."""
    for table, columns in ADDED_COLUMNS.items():
        result = await connection.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result}

        for name, definition in columns:
            if name not in existing:
                await connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                )


async def _rebuild_check_table(connection: AsyncConnection) -> None:
    """
    Rewrites `updatecheck` without the column it no longer uses.

    A database created while the table kept one count has `missing` as NOT NULL
    without a default - SQLite cannot drop such a column, and a row that leaves it
    out is refused ("NOT NULL constraint failed: updatecheck.missing"), which made
    every check fail on such a library. The rows are a cache of the last check,
    which the next one recomputes, so the table is dropped and `create_all` makes
    the current one.
    """
    result = await connection.execute(text("PRAGMA table_info(updatecheck)"))
    existing = {row[1] for row in result}

    if existing and LEGACY_CHECK_COLUMN in existing:
        crologger.info(
            "Library: rebuilding the updatecheck table (it had %s)",
            LEGACY_CHECK_COLUMN,
        )
        await connection.execute(text("DROP TABLE updatecheck"))


async def init_db() -> None:
    """Creates the library tables if they do not exist yet."""
    # Importing the models registers them on SQLModel.metadata.
    from crodl.library import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        await _add_missing_columns(connection)
        await _rebuild_check_table(connection)
        # A table that was rebuilt above comes back in its current shape.
        await connection.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-style session dependency."""
    async with async_session_factory() as session:
        yield session
