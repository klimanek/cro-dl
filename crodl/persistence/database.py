from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from crodl.settings import DATABASE_URL, DB_PATH
from crodl.streams.utils import create_dir_if_does_not_exist

# Vytvoření asynchronního motoru
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async def init_db():
    """Vytvoří databázi a tabulky, pokud neexistují."""
    # Zajistit, že adresář pro DB existuje
    create_dir_if_does_not_exist(DB_PATH.parent)
    
    async with engine.begin() as conn:
        # SQLModel metadata tvoříme asynchronně přes run_sync
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    """Poskytuje asynchronní session pro práci s DB."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
