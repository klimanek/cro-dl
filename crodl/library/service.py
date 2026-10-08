"""Library service: connects the core's download hook to storage and artwork."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from crodl.library.artwork import cover_path, fetch_artwork, fetch_cover
from crodl.library.models import Episode
from crodl.library.repository import DownloadedWork, SqliteLibraryRepository

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

    def __init__(self, repository: Optional[SqliteLibraryRepository] = None) -> None:
        self.repository = repository or SqliteLibraryRepository()
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
        item = LibraryItem(
            type=ctype,
            id=cid,
            title=str(title),
            description=getattr(row, "description", None)
            or ("Soubory bez metadat." if ctype == ORPHANS else None),
            count=len(episodes),
            image_path=self._cover_of(episodes),
        )

        return item, order_episodes(episodes)

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


def collection_key(episode: Episode) -> Optional[tuple[str, str]]:
    """The (type, id) of the collection an episode is filed under, if any."""
    if episode.series_id:
        return "series", episode.series_id
    if episode.show_id:
        return "show", episode.show_id

    return None
