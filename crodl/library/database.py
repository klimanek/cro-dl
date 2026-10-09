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

#: Columns `updatecheck` gained after the table existed. SQLite's `create_all`
#: only ever creates whole tables, so they are added here; the table holds the
#: outcome of a check, which the next one recomputes anyway.
ADDED_COLUMNS = (
    ("available", "INTEGER NOT NULL DEFAULT 0"),
    ("upcoming", "INTEGER NOT NULL DEFAULT 0"),
    ("expired", "INTEGER NOT NULL DEFAULT 0"),
)


async def _add_missing_columns(connection: AsyncConnection) -> None:
    """Adds the columns an older `updatecheck` table does not have yet."""
    result = await connection.execute(text("PRAGMA table_info(updatecheck)"))
    existing = {row[1] for row in result}

    for name, definition in ADDED_COLUMNS:
        if name not in existing:
            await connection.execute(
                text(f"ALTER TABLE updatecheck ADD COLUMN {name} {definition}")
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
