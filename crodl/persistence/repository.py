import asyncio
from typing import Optional, List, Sequence
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
        """
        async with self._lock:
            async with async_session_factory() as session:
                if station_data:
                    await session.merge(station_data)
                if show_data:
                    await session.merge(show_data)
                if series_data:
                    await session.merge(series_data)
                await session.merge(episode_data)
                await session.commit()

    async def get_all_episodes(self) -> Sequence[Episode]:
        """Returns all downloaded episodes."""
        async with async_session_factory() as session:
            statement = select(Episode).order_by(Episode.since.desc())
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_episodes_by_show(self, show_id: str) -> Sequence[Episode]:
        """Returns all episodes belonging to a specific show."""
        async with async_session_factory() as session:
            statement = select(Episode).where(Episode.show_id == show_id).order_by(Episode.since.desc())
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_episodes_by_series(self, series_id: str) -> Sequence[Episode]:
        """Returns all episodes belonging to a specific series."""
        async with async_session_factory() as session:
            statement = select(Episode).where(Episode.series_id == series_id).order_by(Episode.since.desc())
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_all_shows(self) -> Sequence[Show]:
        """Returns all shows that have at least one downloaded episode."""
        async with async_session_factory() as session:
            statement = select(Show)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_all_series(self) -> Sequence[Series]:
        """Returns all series that have at least one downloaded episode."""
        async with async_session_factory() as session:
            statement = select(Series)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_show(self, show_id: str) -> Optional[Show]:
        """Retrieves a single show by its ID."""
        async with async_session_factory() as session:
            statement = select(Show).where(Show.id == show_id)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_series(self, series_id: str) -> Optional[Series]:
        """Retrieves a single series by its ID."""
        async with async_session_factory() as session:
            statement = select(Series).where(Series.id == series_id)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_episode(self, uuid: str) -> Optional[Episode]:
        """Retrieves a single episode by its UUID."""
        async with async_session_factory() as session:
            statement = select(Episode).where(Episode.id == uuid)
            result = await session.execute(statement)
            return result.scalar_one_or_none()
