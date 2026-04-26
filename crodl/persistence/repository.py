import asyncio
from typing import Optional, Sequence
from sqlmodel import select

from crodl.persistence.models import Episode, Show, Series, Station
from crodl.persistence.database import async_session_factory


class LibraryRepository:
    """
    Repository for managing the local library of downloaded content.
    Handles database operations for Episodes, Shows, Series, and Stations.
    Uses an internal lock to prevent race conditions during parallel downloads.
    """

    def __init__(self):
        self._lock = asyncio.Lock()

    async def save_episode(
        self,
        episode_data: Episode,
        show_data: Optional[Show] = None,
        series_data: Optional[Series] = None,
        station_data: Optional[Station] = None,
    ) -> None:
        """
        Saves or updates an episode and its related entities in the database.
        Uses a lock to prevent IntegrityErrors when multiple tasks save shared entities.
        """
        async with self._lock:
            async with async_session_factory() as session:
                # 1. Merge related entities first to handle foreign key constraints
                if station_data:
                    await session.merge(station_data)

                if show_data:
                    await session.merge(show_data)

                if series_data:
                    await session.merge(series_data)

                # 2. Merge the primary episode data
                await session.merge(episode_data)

                await session.commit()

    async def is_downloaded(self, uuid: str) -> bool:
        """
        Checks if an episode with the given UUID already exists in the database.
        """
        async with async_session_factory() as session:
            statement = select(Episode).where(Episode.id == uuid)
            result = await session.execute(statement)
            return result.first() is not None

    async def get_episode(self, uuid: str) -> Optional[Episode]:
        """
        Retrieves a single episode by its UUID.
        """
        async with async_session_factory() as session:
            statement = select(Episode).where(Episode.id == uuid)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_all_episodes(self) -> Sequence[Episode]:
        """
        Returns all downloaded episodes from the database.
        Useful for the web library interface.
        """
        async with async_session_factory() as session:
            statement = select(Episode)
            result = await session.execute(statement)
            return result.scalars().all()
