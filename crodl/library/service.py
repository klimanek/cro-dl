"""Library service: connects the core's download hook to storage and artwork."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from crodl.data.attributes import extract_asset_url, extract_genre, extract_parent
from crodl.library import roots
from crodl.library.artwork import cover_path, fetch_artwork, fetch_cover
from crodl.library.models import Episode, LibraryRoot, UpdateCheck, WorkLink
from crodl.library.refresh import LibraryRefresh, Refresh, api_id
from crodl.library.repository import DownloadedWork, SqliteLibraryRepository
from crodl.library.scan import LibraryScan
from crodl.library.tags import write_tags
from crodl.library.updates import LibraryUpdates, NewPart
from crodl.program.content import Collection
from crodl.settings import DOWNLOAD_PATH, SUPPORTED_DOMAINS
from crodl.streams.utils import remove_html_tags
from crodl.tools.logger import crologger

#: Hosts whose pages cro-dl can read (a work's link must point at one).
SUPPORTED_HOSTS = {domain.replace("www.", "") for domain in SUPPORTED_DOMAINS}

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
    #: The work's genre, used for the parts' tags and the genre menu.
    genre: Optional[str] = None
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
        """Stores a finished download, its artwork, its work - and its tags."""
        if collection is None:
            # A one-off episode arrives without a work of its own; the API names
            # the show it was aired in, and that is where its file belongs.
            collection = await self._parent_collection(work)

        image_path = await self._artwork(work, path, collection)

        episode = await self.repository.save_download(
            work,
            path,
            audio_format=audio_format,
            image_path=image_path,
            collection=collection,
        )

        # What a player reads belongs in the file, not only in our database.
        await write_tags(
            path,
            title=work.title,
            author=work.author,
            album=collection.title if collection else None,
            genre=collection.genre if collection else None,
            track=work.part,
        )

        return episode

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
                    genre=row.genre if row else None,
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

    async def genres(self) -> list[str]:
        """Every genre the library knows, for the genre menu in the top bar."""
        rows = [
            *await self.repository.get_all_shows(),
            *await self.repository.get_all_series(),
        ]

        return sorted({str(row.genre) for row in rows if row.genre}, key=str.casefold)

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
            genre=getattr(row, "genre", None) if row else None,
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
        Applies hand-edited metadata to a work (title, genre, description).

        A work that was adopted from disk is named after its folder; this is how
        it gets the name a person would give it. A blank title leaves the work as
        it is - an unnamed work cannot be shown - while a blank genre or
        description clears what was there. Returns False only when there is no
        such work.
        """
        changes = _changes(fields, ("title", "genre", "description"))

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
        know, and the artwork whose download failed earlier). Works for a work
        the API knows by its own uuid and for one whose page somebody added (see
        `set_source_url`); None when there is no API record to ask about.

        The files that belong to no work ("Místní soubory") are the exception:
        there, each part's own record says which work it aired in, and asking is
        what links it (`link_loose_parts`).
        """
        if ctype == ORPHANS:
            return Refresh(fields=await self.link_loose_parts())

        return await self.refresher.refresh_work(ctype, cid)

    async def set_source_url(
        self, ctype: str, cid: str, url: str
    ) -> Optional[WorkLink]:
        """
        Remembers the mujrozhlas.cz page a work came from.

        Only a page cro-dl can read is accepted; None otherwise, and an empty
        value forgets the link. The work keeps its own key - the link is a
        source, not a new identity.
        """
        url = url.strip()

        if not url:
            return None

        parsed = urlparse(url)
        host = parsed.netloc.replace("www.", "")
        if parsed.scheme not in ("http", "https") or host not in SUPPORTED_HOSTS:
            return None

        return await self.repository.save_work_link(
            WorkLink(collection_id=cid, collection_type=ctype, source_url=url)
        )

    async def source_url(self, cid: str) -> Optional[str]:
        """The page a work came from, if somebody added one."""
        link = await self.repository.get_work_link(cid)

        return link.source_url if link else None

    async def write_work_tags(self, ctype: str, cid: str) -> int:
        """
        Writes what the library knows into every part's file; how many took it.

        For files that were downloaded before cro-dl tagged anything, or whose
        file was replaced: the work's title becomes the album, the work's genre
        the genre, and the part brings its own title, author and number. A file
        keeps a genre nobody typed for its work (`write_tags` only writes what it
        is given).
        """
        content, episodes = await self.detail(ctype, cid)
        if content is None or not episodes:
            return 0

        written = 0
        for episode in episodes:
            if not episode.local_path:
                continue

            if await write_tags(
                Path(episode.local_path),
                title=episode.title,
                author=episode.author,
                album=content.title,
                genre=content.genre,
                track=episode.part,
            ):
                written += 1

        crologger.info(
            "Library: tagged %s of %s files of %s", written, len(episodes), cid
        )
        return written

    async def write_part_tags(
        self,
        path: Path,
        *,
        title: Optional[str] = None,
        author: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        track: Optional[int] = None,
    ) -> bool:
        """Writes the tags a person edited for one part into its file."""
        return await write_tags(
            path, title=title, author=author, album=album, genre=genre, track=track
        )

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

        Only what the library stored is handed out - a library folder also holds
        the segment folders, the log and the database itself, none of which
        belong in a URL. A path that tries to leave a folder is refused. The
        path is relative to one of the folders the library keeps, so a second
        folder on an external disk is served the same way.
        """
        parts = Path(relative_path).parts

        if Path(relative_path).is_absolute() or ".." in parts:
            return None

        for root in dict.fromkeys([self.download_path, *roots.known()]):
            target = root.joinpath(*parts)

            if target.is_file() and await self.repository.knows_file(target):
                return target

        return None

    async def load_roots(self) -> None:
        """
        Loads the folders the library keeps, seeding the default one.

        Called when the server starts, so the pages can tell (without asking the
        database per part) which files may be served and whether a folder is
        missing right now.
        """
        stored = await self.repository.get_roots()

        if not stored:
            stored = [
                await self.repository.save_root(LibraryRoot(path=str(DOWNLOAD_PATH)))
            ]

        roots.load([row.path for row in stored])

    async def add_root(self, path: str) -> Optional[LibraryRoot]:
        """
        Registers a folder of audio; None when it cannot be read.

        The folder has to be there and be a directory - an external disk that is
        not plugged in is what the page then says.
        """
        folder = Path(path.strip()).expanduser()

        if not path.strip() or not folder.is_dir():
            return None

        stored = await self.repository.save_root(LibraryRoot(path=str(folder)))
        roots.register(folder)
        crologger.info("Library: added root %s", folder)

        return stored

    async def import_root(self, path: str) -> dict[str, int]:
        """Scans a folder into the library; the counts come from the scan."""
        result = await LibraryScan(
            repository=self.repository, download_path=Path(path)
        ).sync_all()

        crologger.info("Library: imported %s (%s)", path, result)
        return result

    async def forget_root(self, path: str) -> bool:
        """Forgets a folder; the works that came from it stay in the library."""
        if not await self.repository.delete_root(path):
            return False

        roots.forget(Path(path))
        return True

    def known_roots(self) -> list[Path]:
        """The folders the library keeps its audio in."""
        return roots.known()

    async def stored_roots(self) -> list[LibraryRoot]:
        """The folders as the database holds them, oldest first."""
        return list(await self.repository.get_roots())

    def missing_roots(self) -> list[Path]:
        """The folders that are not there right now (an unplugged disk)."""
        return roots.missing()

    async def _parent_collection(self, work: DownloadedWork) -> Optional["Collection"]:
        """
        The work an episode was aired in, so its file is not left without one.

        The relationship carries only a uuid, so the work's own record is fetched
        for its title - and, for free, for the description, the genre and the
        artwork its parts should share. One request, and only when a download
        arrives with no work of its own.
        """
        return await self._collection_for(work.parent)

    async def _collection_for(
        self, parent: Optional[tuple[str, str]]
    ) -> Optional["Collection"]:
        """The work a record names, fetched for what its parts should share."""
        if parent is None:
            return None

        ctype, uuid = parent
        fetch = (
            self.refresher.client.get_series_data
            if ctype == "series"
            else self.refresher.client.get_show_data
        )

        try:
            data = await asyncio.to_thread(fetch, uuid)
        except Exception as error:  # the API is the network: it may be away
            crologger.warning("Could not read the work behind %s: %s", uuid, error)
            return None

        record = (data or {}).get("data") or {}
        attributes = record.get("attributes") or {}
        title = attributes.get("title")

        if not title:
            return None

        crologger.info("Library: %s is the work behind a part", title)

        return Collection(
            uuid=uuid,
            type=ctype,
            title=str(title),
            description=remove_html_tags(str(attributes.get("description") or ""))
            or None,
            shared_asset_url=extract_asset_url(record),
            genre=extract_genre(data),
        )

    async def link_loose_parts(self) -> int:
        """
        Files the library kept without a work: ask the API which work each aired in.

        Downloads that arrived before cro-dl read the API's relationships sit in
        "Místní soubory" although the record of the part names the show (or
        serial) it belongs to. One request per loose part; a file the API does
        not know is left where it is.
        """
        linked = 0

        for episode in await self.repository.get_all_episodes():
            if episode.show_id or episode.series_id or not api_id(episode.uuid):
                continue

            collection = await self._collection_for(
                await self._parent_of_part(episode.uuid)
            )

            if collection is None:
                continue

            await self.repository.link_episode(episode.uuid, collection)
            linked += 1

        crologger.info("Library: linked %s loose parts to their works", linked)
        return linked

    async def _parent_of_part(self, uuid: str) -> Optional[tuple[str, str]]:
        """The work the API says a part belongs to (a record carries only a uuid)."""
        try:
            data = await asyncio.to_thread(self.refresher.client.get_episode_data, uuid)
        except Exception as error:
            crologger.warning("Could not read part %s: %s", uuid, error)
            return None

        return extract_parent(data or {})

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
