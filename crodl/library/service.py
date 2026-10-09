"""Library service: connects the core's download hook to storage and artwork."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from crodl.library.artwork import cover_path, fetch_artwork, fetch_cover
from crodl.library.models import Episode, UpdateCheck
from crodl.library.refresh import LibraryRefresh, Refresh, api_id
from crodl.library.repository import DownloadedWork, SqliteLibraryRepository
from crodl.library.updates import LibraryUpdates, NewPart
from crodl.settings import DOWNLOAD_PATH

if TYPE_CHECKING:
    from crodl.program.content import Collection

# The library's bucket for files that belong to no show or series.
ORPHANS = "orphans"
ORPHANS_TITLE = "Místní soubory"


@dataclass(frozen=True)
class LibraryItem:
    """One work of the library, the way the web grid lists it."""

    # "show", "series", or ORPHANS for files without a collection.
    type: str
    id: str
    title: str
    description: Optional[str] = None
    count: int = 0
    # Artwork of the work, on disk; the web layer turns it into a URL.
    image_path: Optional[str] = None
    #: Whether a Czech Radio id is behind it (a folder adopted from disk is not).
    from_api: bool = False
    #: Missing parts by state: fetchable now, not aired yet, gone for good.
    available: int = 0
    upcoming: int = 0
    expired: int = 0
    #: When the work was last looked at for new parts.
    checked_at: Optional[datetime] = None


def order_episodes(episodes: Sequence[Episode]) -> list[Episode]:
    """
    The parts of a work in the order they should be played.

    A collection whose parts are numbered (a reading, a series) reads by that
    number; a show's episodes carry no number, so the newest comes first.
    """
    if any(episode.part is not None for episode in episodes):
        return sorted(
            episodes,
            key=lambda episode: (
                episode.part is None,
                episode.part or 0,
                episode.broadcast_at or datetime.min,
            ),
        )

    return sorted(
        episodes,
        key=lambda episode: episode.broadcast_at or datetime.min,
        reverse=True,
    )


class LibraryService:
    """
    Orchestration over `SqliteLibraryRepository`.

    This is what the facade hands to the core's `on_downloaded` hook: the core
    reports a finished file, the service fetches its artwork, links it to the
    show/series it belongs to and stores both. It also answers what the web
    library shows, so the route handlers stay free of domain logic.
    """

    def __init__(
        self,
        repository: Optional[SqliteLibraryRepository] = None,
        download_path: Path = DOWNLOAD_PATH,
        refresher: Optional[LibraryRefresh] = None,
        updates: Optional[LibraryUpdates] = None,
    ) -> None:
        self.repository = repository or SqliteLibraryRepository()
        # Where the media the web layer serves live (injectable for tests).
        self.download_path = download_path
        # Asks the content API for what the library is missing (see `refresh`).
        self.refresher = refresher or LibraryRefresh(repository=self.repository)
        # Looks for parts the Czech Radio has released since (see `check_for_new_parts`).
        self.updates = updates or LibraryUpdates(repository=self.repository)
        # Parts of one work are downloaded in parallel and share their cover,
        # so a lock per target keeps them from writing the same file twice.
        self._artwork_locks: dict[Path, asyncio.Lock] = {}

    async def save_download(
        self,
        work: DownloadedWork,
        path: Path,
        audio_format: Optional[str] = None,
        collection: Optional["Collection"] = None,
    ) -> Optional[Episode]:
        """Stores a finished download together with its artwork and collection."""
        image_path = await self._artwork(work, path, collection)

        return await self.repository.save_download(
            work,
            path,
            audio_format=audio_format,
            image_path=image_path,
            collection=collection,
        )

    async def overview(self) -> list[LibraryItem]:
        """Every work of the library, sorted by title, orphans last."""
        episodes = await self.repository.get_all_episodes()
        shows = {row.uuid: row for row in await self.repository.get_all_shows()}
        series = {row.uuid: row for row in await self.repository.get_all_series()}

        grouped: dict[tuple[str, str], list[Episode]] = {}
        orphans: list[Episode] = []

        for episode in episodes:
            key = collection_key(episode)
            if key is None:
                orphans.append(episode)
            else:
                grouped.setdefault(key, []).append(episode)

        items = []
        checks = {
            check.collection_id: check
            for check in await self.repository.get_update_checks()
        }

        for (ctype, cid), parts in grouped.items():
            row = shows.get(cid) if ctype == "show" else series.get(cid)
            items.append(
                LibraryItem(
                    type=ctype,
                    id=cid,
                    title=row.title if row else cid,
                    description=row.description if row else None,
                    count=len(parts),
                    image_path=self._cover_of(parts),
                    from_api=api_id(cid),
                    **check_fields(cid, checks),
                )
            )

        items.sort(key=lambda item: item.title.casefold())

        if orphans:
            items.append(
                LibraryItem(
                    type=ORPHANS,
                    id=ORPHANS,
                    title=ORPHANS_TITLE,
                    description="Soubory, které nepatří k žádnému pořadu ani seriálu.",
                    count=len(orphans),
                    image_path=self._cover_of(orphans),
                )
            )

        return items

    async def detail(
        self, ctype: str, cid: str
    ) -> tuple[Optional[LibraryItem], list[Episode]]:
        """
        One work with its parts. Returns (None, []) when it is not in the library.

        `ctype` is what the web layer puts in the URL: "show", "series" or
        "orphans".
        """
        row: Optional[object] = None

        if ctype == "show":
            row = await self.repository.get_show(cid)
            episodes = await self.repository.get_episodes_by_show(cid)
        elif ctype == "series":
            row = await self.repository.get_series(cid)
            episodes = await self.repository.get_episodes_by_series(cid)
        elif ctype == ORPHANS:
            episodes = [
                episode
                for episode in await self.repository.get_all_episodes()
                if collection_key(episode) is None
            ]
        else:
            return None, []

        if ctype != ORPHANS and row is None:
            return None, []

        title = getattr(row, "title", ORPHANS_TITLE)
        checks = {
            check.collection_id: check
            for check in await self.repository.get_update_checks()
        }
        item = LibraryItem(
            type=ctype,
            id=cid,
            title=str(title),
            description=getattr(row, "description", None)
            or ("Soubory bez metadat." if ctype == ORPHANS else None),
            count=len(episodes),
            image_path=self._cover_of(episodes),
            from_api=api_id(cid),
            **check_fields(cid, checks),
        )

        return item, order_episodes(episodes)

    async def curate_work(
        self, ctype: str, cid: str, fields: Mapping[str, str]
    ) -> bool:
        """
        Applies hand-edited metadata to a work (title, description).

        A work that was adopted from disk is named after its folder; this is how
        it gets the name a person would give it. A blank title leaves the work as
        it is - an unnamed work cannot be shown - while a blank description
        clears what was there. Returns False only when there is no such work.
        """
        changes = _changes(fields, ("title", "description"))

        if ctype == "show":
            row = await self.repository.update_show(cid, changes)
        elif ctype == "series":
            row = await self.repository.update_series(cid, changes)
        else:
            return False

        return row is not None

    async def curate_part(self, uuid: str, fields: Mapping[str, str]) -> bool:
        """
        Applies hand-edited metadata to one part of a work.

        Returns False only when there is no such part.
        """
        return (
            await self.repository.update_episode(
                uuid, _changes(fields, ("title", "author", "description"))
            )
            is not None
        )

    async def forget(self, ctype: str, cid: str) -> int:
        """
        Removes a work (or the files that belong to no work) from the library.

        Only the records go: the audio and the covers stay on disk, so a
        `--sync` adopts them again. Returns how many rows were removed.
        """
        return await self.repository.delete_work(ctype, cid)

    async def refresh(self, ctype: str, cid: str) -> Optional[Refresh]:
        """
        Asks the content API what this work still has for us.

        Fills in what the library is missing (metadata that a scan could not
        know, and the artwork whose download failed earlier); None when there is
        no API record to ask about.
        """
        return await self.refresher.refresh_work(ctype, cid)

    async def check_for_new_parts(self) -> int:
        """
        Looks for parts the Czech Radio has released since; returns how many works gained one.

        The answer is remembered, so the grid can show a badge until the parts
        are fetched (or the work is looked at again).
        """
        return await self.updates.check_all()

    async def check_work(self, ctype: str, cid: str) -> Optional[UpdateCheck]:
        """Looks at one work and remembers what it is missing (None if unknown)."""
        return await self.updates.check_work(ctype, cid)

    async def missing_parts(self, ctype: str, cid: str) -> Optional[list[NewPart]]:
        """The parts the API has that this work does not."""
        return await self.updates.missing_parts(ctype, cid)

    async def media_file(self, relative_path: str) -> Optional[Path]:
        """
        The file the library keeps at `relative_path`, ready to be served.

        Only what the library stored is handed out - the download directory also
        holds the segment folders, the log and the database itself, none of which
        belong in a URL. A path that tries to leave that directory is refused.
        """
        parts = Path(relative_path).parts

        if Path(relative_path).is_absolute() or ".." in parts:
            return None

        target = self.download_path.joinpath(*parts)

        if not target.is_file() or not await self.repository.knows_file(target):
            return None

        return target

    async def _artwork(
        self,
        work: DownloadedWork,
        path: Path,
        collection: Optional["Collection"],
    ) -> Optional[Path]:
        """The cover the parts of a work share, or this part's own image."""
        shared_url = collection.shared_asset_url if collection else None

        if shared_url:
            return await self._shared_cover(shared_url, path.parent)

        return await fetch_artwork(work.asset_url, path)

    async def _shared_cover(self, url: str, directory: Path) -> Optional[Path]:
        """Fetches a work's cover once - later parts and runs reuse the file."""
        target = cover_path(url, directory)
        lock = self._artwork_locks.setdefault(target, asyncio.Lock())

        async with lock:
            if target.exists():
                return target

            return await fetch_cover(url, directory)

    @staticmethod
    def _cover_of(episodes: Sequence[Episode]) -> Optional[str]:
        """The first part that has artwork stands for the whole work."""
        for episode in episodes:
            if episode.image_path:
                return episode.image_path

        return None


def _changes(
    fields: Mapping[str, str], editable: tuple[str, ...]
) -> dict[str, Optional[str]]:
    """
    The columns a form actually changes.

    Values are trimmed and an empty one means "nothing": a blank title is no edit
    at all (an unnamed work cannot be shown), while a blank author or description
    clears that column.
    """
    changes: dict[str, Optional[str]] = {}

    for field in editable:
        value = fields.get(field)
        if value is None:
            continue

        text = value.strip()
        if text:
            changes[field] = text
        elif field != "title":
            changes[field] = None

    return changes


def collection_key(episode: Episode) -> Optional[tuple[str, str]]:
    """The (type, id) of the collection an episode is filed under, if any."""
    if episode.series_id:
        return "series", episode.series_id
    if episode.show_id:
        return "show", episode.show_id

    return None


def check_fields(cid: str, checks: Mapping[str, UpdateCheck]) -> dict[str, Any]:
    """What the last look for new parts says about a work, for `LibraryItem`."""
    check = checks.get(cid)

    return {
        "available": check.available if check else 0,
        "upcoming": check.upcoming if check else 0,
        "expired": check.expired if check else 0,
        "checked_at": check.checked_at if check else None,
    }
