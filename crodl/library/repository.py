import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, TYPE_CHECKING, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from crodl.library.database import async_session_factory
from crodl.library.models import Episode, Series, Show, Station
from crodl.tools.logger import crologger

if TYPE_CHECKING:
    from crodl.program.content import Collection


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

    @property
    def asset_url(self) -> Optional[str]: ...


@runtime_checkable
class DownloadStore(Protocol):
    """
    The only thing the core's `on_downloaded` hook needs: store one finished
    download. Anything that can do this may be handed to the facade.
    """

    async def save_download(
        self,
        work: DownloadedWork,
        path: Path,
        audio_format: Optional[str] = None,
        collection: Optional["Collection"] = None,
    ) -> Optional[Episode]: ...


@runtime_checkable
class LibraryRepository(DownloadStore, Protocol):
    """Storage for downloaded works. The core never talks SQL directly."""

    async def get_all_downloads(self) -> Sequence[Episode]:
        """Returns every work kept in the library."""
        ...

    async def knows_file(self, path: Path) -> bool:
        """True when this local file is part of the library and may be served."""
        ...

    async def update_show(self, uuid: str, changes: dict[str, Any]) -> Optional[Show]:
        """Applies the given columns to a stored show, leaving the rest alone."""
        ...

    async def update_series(
        self, uuid: str, changes: dict[str, Any]
    ) -> Optional[Series]:
        """Applies the given columns to a stored series, leaving the rest alone."""
        ...

    async def update_episode(
        self, uuid: str, changes: dict[str, Any]
    ) -> Optional[Episode]:
        """Applies the given columns to a stored episode, leaving the rest alone."""
        ...

    async def delete_work(self, ctype: str, cid: str) -> int:
        """Removes a work (and its parts) from the library; returns rows deleted."""
        ...

    async def find_episode_by_path(self, path: Path) -> Optional[Episode]:
        """The stored row for a file on disk, whatever key it was saved under."""
        ...

    async def link_episode(self, uuid: str, collection: Optional["Collection"]) -> None:
        """Files an already stored episode under a collection."""
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

    # The only columns hand curation may rewrite: everything else (paths, keys,
    # durations) comes from the API or from disk.
    CURATED_FIELDS = frozenset({"title", "author", "description"})

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] = async_session_factory,
    ) -> None:
        self._session_factory = session_factory
        # Writes arrive from parallel episode downloads; SQLite needs them serialized.
        self._lock = asyncio.Lock()

    async def save_download(
        self,
        work: DownloadedWork,
        path: Path,
        audio_format: Optional[str] = None,
        image_path: Optional[Path] = None,
        station_id: Optional[str] = None,
        show_id: Optional[str] = None,
        series_id: Optional[str] = None,
        is_manual: bool = False,
        source_url: Optional[str] = None,
        collection: Optional["Collection"] = None,
    ) -> Optional[Episode]:
        if not work.uuid:
            crologger.warning("Not saving '%s' to the library: no uuid.", work.title)
            return None

        if collection is not None and collection.uuid:
            if collection.type == "series":
                series_id = series_id or collection.uuid
            else:
                show_id = show_id or collection.uuid

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
            image_path=str(image_path) if image_path else None,
            audio_format=audio_format,
            is_manual=is_manual,
            source_url=source_url,
            station_id=station_id,
            show_id=show_id,
            series_id=series_id,
            meta=self._build_meta(work),
        )

        async with self._lock:
            async with self._session_factory() as session:
                if collection is not None and collection.uuid:
                    await self._upsert_collection(session, collection)
                # merge() makes this an upsert on the primary key.
                await session.merge(episode)
                await session.commit()

        crologger.info("Library: saved %s", episode.uuid)
        return episode

    async def find_episode_by_path(self, path: Path) -> Optional[Episode]:
        """
        The stored row for a file on disk, whatever key it was saved under.

        A download is keyed by its Czech Radio uuid, a scanned file by its
        path, so re-scanning the download directory would otherwise file the
        same audio twice.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Episode).where(Episode.local_path == str(path))
            )
            return result.scalars().first()

    async def knows_file(self, path: Path) -> bool:
        """
        True when this local file is part of the library, so it may be served.

        Audio is stored as `local_path`, artwork as `image_path`. Everything
        else in the download directory - the segment folders, the log, the
        database itself - is not in here and stays out of reach.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Episode)
                .where(
                    (Episode.local_path == str(path))
                    | (Episode.image_path == str(path))
                )
                .limit(1)
            )
            return result.scalars().first() is not None

    async def link_episode(self, uuid: str, collection: Optional["Collection"]) -> None:
        """
        Files an already stored episode under a collection.

        Used by the disk scan for files that are in the library but not yet
        linked to a show/series; an episode that already belongs to one keeps
        it, as does one whose collection is unknown.
        """
        if collection is None or not collection.uuid:
            return

        async with self._lock:
            async with self._session_factory() as session:
                episode = await session.get(Episode, uuid)

                if episode is None or episode.show_id or episode.series_id:
                    return

                if collection.type == "series":
                    episode.series_id = collection.uuid
                else:
                    episode.show_id = collection.uuid

                await self._upsert_collection(session, collection)
                session.add(episode)
                await session.commit()

        crologger.info("Library: linked %s to %s", uuid, collection.title)

    async def _upsert_collection(
        self, session: AsyncSession, collection: "Collection"
    ) -> None:
        """Makes sure the show/series exists, so its parts can point at it."""
        if collection.type == "series":
            await session.merge(
                Series(
                    uuid=collection.uuid,
                    title=collection.title,
                    description=collection.description,
                )
            )
        else:
            await session.merge(
                Show(
                    uuid=collection.uuid,
                    title=collection.title,
                    description=collection.description,
                )
            )

    async def save_station(self, station: Station) -> Station:
        return await self._upsert(station)

    async def save_episode(self, episode: Episode) -> Episode:
        """Stores a hand-built episode row (used by the scan and manual import)."""
        return await self._upsert(episode)

    async def save_show(self, show: Show) -> Show:
        return await self._upsert(show)

    async def save_series(self, series: Series) -> Series:
        return await self._upsert(series)

    async def get_all_downloads(self) -> Sequence[Episode]:
        """Alias of `get_all_episodes`, kept for the core-facing protocol."""
        return await self.get_all_episodes()

    async def get_all_episodes(self) -> Sequence[Episode]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Episode).order_by(col(Episode.broadcast_at).desc())
            )
            return result.scalars().all()

    async def get_episode(self, uuid: str) -> Optional[Episode]:
        async with self._session_factory() as session:
            return await session.get(Episode, uuid)

    async def get_episodes_by_show(self, show_id: str) -> Sequence[Episode]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Episode)
                .where(Episode.show_id == show_id)
                .order_by(col(Episode.broadcast_at).desc())
            )
            return result.scalars().all()

    async def get_episodes_by_series(self, series_id: str) -> Sequence[Episode]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Episode)
                .where(Episode.series_id == series_id)
                .order_by(col(Episode.broadcast_at).desc())
            )
            return result.scalars().all()

    async def get_all_shows(self) -> Sequence[Show]:
        async with self._session_factory() as session:
            result = await session.execute(select(Show))
            return result.scalars().all()

    async def get_all_series(self) -> Sequence[Series]:
        async with self._session_factory() as session:
            result = await session.execute(select(Series))
            return result.scalars().all()

    async def get_show(self, show_id: str) -> Optional[Show]:
        async with self._session_factory() as session:
            return await session.get(Show, show_id)

    async def get_series(self, series_id: str) -> Optional[Series]:
        async with self._session_factory() as session:
            return await session.get(Series, series_id)

    async def update_show(self, uuid: str, changes: dict[str, Any]) -> Optional[Show]:
        """Applies the given columns to a stored show, leaving the rest alone."""
        return await self._update_row(Show, uuid, changes)

    async def update_series(
        self, uuid: str, changes: dict[str, Any]
    ) -> Optional[Series]:
        """Applies the given columns to a stored series, leaving the rest alone."""
        return await self._update_row(Series, uuid, changes)

    async def update_episode(
        self, uuid: str, changes: dict[str, Any]
    ) -> Optional[Episode]:
        """
        Applies the given columns to a stored episode, leaving the rest alone.

        `save_download()` cannot do this: it builds a whole row from a finished
        download and `merge()` would blank whatever the caller left out.
        """
        return await self._update_row(Episode, uuid, changes)

    async def delete_work(self, ctype: str, cid: str) -> int:
        """
        Removes a work and its parts from the library; returns the rows deleted.

        Only the library's records go - the audio and the covers stay on disk, so
        a `--sync` would adopt them again. `ctype` is "show", "series", or
        "orphans" for the files that belong to no work.
        """
        if ctype not in ("show", "series", "orphans"):
            return 0

        async with self._lock:
            async with self._session_factory() as session:
                row: Any = None
                if ctype == "show":
                    row = await session.get(Show, cid)
                elif ctype == "series":
                    row = await session.get(Series, cid)

                if ctype != "orphans" and row is None:
                    return 0

                episodes = await self._episodes_of(session, ctype, cid)

                for episode in episodes:
                    await session.delete(episode)
                if row is not None:
                    await session.delete(row)

                await session.commit()

        deleted = len(episodes) + (1 if row is not None else 0)
        crologger.info("Library: removed %s (%s rows)", cid, deleted)

        return deleted

    async def _episodes_of(
        self, session: AsyncSession, ctype: str, cid: str
    ) -> Sequence[Episode]:
        """The parts of a work, or the files that belong to no work at all."""
        if ctype == "orphans":
            # `col()` for the same reason as in the ordering above: on the class
            # the attribute reads as a value, not as a column to compare.
            condition = col(Episode.show_id).is_(None) & col(Episode.series_id).is_(
                None
            )
        elif ctype == "series":
            condition = Episode.series_id == cid
        else:
            condition = Episode.show_id == cid

        result = await session.execute(select(Episode).where(condition))

        return result.scalars().all()

    async def _update_row(
        self, model: type[Any], uuid: str, changes: dict[str, Any]
    ) -> Optional[Any]:
        """Writes hand-curated columns onto one row; None if it does not exist."""
        unknown = set(changes) - self.CURATED_FIELDS
        if unknown:
            raise ValueError(f"Cannot curate: {', '.join(sorted(unknown))}")

        async with self._lock:
            async with self._session_factory() as session:
                row = await session.get(model, uuid)

                if row is None:
                    return None

                for field, value in changes.items():
                    setattr(row, field, value)

                if changes:
                    session.add(row)
                    await session.commit()

        if changes:
            crologger.info("Library: curated %s", uuid)

        return row

    async def _upsert(self, row: Any) -> Any:
        async with self._lock:
            async with self._session_factory() as session:
                await session.merge(row)
                await session.commit()
        return row

    @staticmethod
    def _build_meta(work: DownloadedWork) -> dict[str, Any]:
        """Whatever we cannot map onto a column is kept as JSON."""
        return {"variants": list(work.audio_formats or []), "since": work.since}
