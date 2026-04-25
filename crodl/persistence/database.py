from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from crodl.settings import DATABASE_URL, DB_PATH
from crodl.streams.utils import create_dir_if_does_not_exist

# Create asynchronous engine
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db() -> None:
    """Initializes the database and creates tables if they do not exist."""
    if not DB_PATH.parent.exists():
        create_dir_if_does_not_exist(DB_PATH.parent)
    
    async with engine.begin() as conn:
        # SQLModel metadata needs to be created via run_sync in async context
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an asynchronous session for database operations."""
    async with async_session_factory() as session:
        yield session
