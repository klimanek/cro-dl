from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crodl.library.database import async_session_factory
from crodl.library.models import Episode
from crodl.tools.logger import crologger


class DownloadedWork(Protocol):
    """
    Everything the library needs to know about a work that was downloaded.

    Members are read-only properties on purpose: the core exposes `description`
    and `author` as properties, and a protocol with mutable attributes would
    reject them as invariant.
    """

    @property
    def uuid(self) -> Optional[str]: ...

    @property
    def title(self) -> str: ...

    @property
    def short_title(self) -> Optional[str]: ...

    @property
    def part(self) -> Optional[int]: ...

    @property
    def duration(self) -> Optional[int]: ...

    @property
    def since(self) -> str: ...

    @property
    def description(self) -> Optional[str]: ...

    @property
    def author(self) -> Optional[str]: ...

    @property
    def audio_formats(self) -> Optional[list[str]]: ...


@runtime_checkable
class LibraryRepository(Protocol):
    """Storage for downloaded works. The core never talks SQL directly."""

    async def save_download(
        self, work: DownloadedWork, path: Path, audio_format: Optional[str] = None
    ) -> Optional[Episode]:
        """Stores (or updates) one downloaded work. Returns None if it has no uuid."""
        ...

    async def get_all_downloads(self) -> Sequence[Episode]:
        """Returns every work kept in the library."""
        ...


def parse_since(value: str) -> Optional[datetime]:
    """Turns the API's `since` string into a timezone-aware datetime."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        crologger.warning("Could not parse 'since': %s", value)
        return None


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite keeps no offset, so timestamps are stored as naive UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class SqliteLibraryRepository:
    """
    SQLite implementation of `LibraryRepository`, backed by SQLModel.

    The session factory is injectable so tests can run against an in-memory
    database instead of the real `~/Z Rozhlasu/library.db`.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] = async_session_factory,
    ) -> None:
        self._session_factory = session_factory

    async def save_download(
        self,
        work: DownloadedWork,
        path: Path,
        audio_format: Optional[str] = None,
    ) -> Optional[Episode]:
        if not work.uuid:
            crologger.warning("Not saving '%s' to the library: no uuid.", work.title)
            return None

        episode = Episode(
            uuid=work.uuid,
            title=work.title,
            short_title=work.short_title,
            part=work.part,
            author=work.author,
            description=work.description,
            duration=work.duration,
            broadcast_at=to_naive_utc(parse_since(work.since)),
            local_path=str(path),
            audio_format=audio_format,
            meta=self._build_meta(work),
        )

        async with self._session_factory() as session:
            # merge() makes this an upsert on the primary key.
            await session.merge(episode)
            await session.commit()

        crologger.info("Library: saved %s", episode.uuid)
        return episode

    async def get_all_downloads(self) -> Sequence[Episode]:
        async with self._session_factory() as session:
            result = await session.execute(select(Episode))
            return result.scalars().all()

    @staticmethod
    def _build_meta(work: DownloadedWork) -> dict[str, Any]:
        """Whatever we cannot map onto a column is kept as JSON."""
        return {"variants": list(work.audio_formats or []), "since": work.since}
