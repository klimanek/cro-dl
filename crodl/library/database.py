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

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

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


async def init_db() -> None:
    """Creates the library tables if they do not exist yet."""
    # Importing the models registers them on SQLModel.metadata.
    from crodl.library import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        await _add_missing_columns(connection)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-style session dependency."""
    async with async_session_factory() as session:
        yield session
