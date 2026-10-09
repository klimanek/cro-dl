"""Filling in what the library is missing, from the content API."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from crodl.data.attributes import extract_asset_url, extract_genre
from crodl.library.artwork import cover_path, fetch_cover
from crodl.library.models import Episode
from crodl.library.repository import (
    SqliteLibraryRepository,
    parse_since,
    to_naive_utc,
)
from crodl.streams.utils import remove_html_tags
from crodl.tools.api_client import CroAPIClient
from crodl.tools.logger import crologger

#: What a refresh may take from the API, per episode.
EPISODE_FIELDS = ("author", "description", "short_title", "duration", "part")

#: The kinds of record the content API keeps, in the order a refresh asks about
#: them (a uuid does not say which it is - see `LibraryRefresh._entity`).
ENTITY_FETCHES = ("get_series_data", "get_show_data", "get_episode_data")


@dataclass
class Refresh:
    """What asking the API for a work's data changed."""

    fields: int = 0
    images: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.fields or self.images)


def api_id(value: Optional[str]) -> bool:
    """
    Whether an id could be a Czech Radio uuid.

    A work adopted from disk is keyed by a hash of its path, which the content
    API has never heard of; those records have nothing to refresh.
    """
    return bool(value) and len(value or "") == 36 and (value or "").count("-") == 4


class LibraryRefresh:
    """
    Asks the content API for what one work is still missing.

    Only *missing* values are written: a title or description somebody edited by
    hand stays as it is, and an episode that already has artwork keeps it. The
    API client is synchronous, so its calls are handed to a thread - the server
    keeps serving the rest of the library while a work is refreshed.
    """

    def __init__(
        self,
        repository: Optional[SqliteLibraryRepository] = None,
        client: Optional[CroAPIClient] = None,
    ) -> None:
        self.repository = repository or SqliteLibraryRepository()
        self.client = client or CroAPIClient()

    async def refresh_work(self, ctype: str, cid: str) -> Optional[Refresh]:
        """
        Fills a work and its parts in from the API; None if there is nothing to ask.

        Returns what was filled in, so the page can say so.
        """
        if ctype not in ("show", "series"):
            return None

        api_uuid = await self._api_uuid(ctype, cid)
        if api_uuid is None:
            return None

        work = (
            await self.repository.get_series(cid)
            if ctype == "series"
            else await self.repository.get_show(cid)
        )

        if work is None:
            return None

        record = await self._record(api_uuid)
        if record is None:
            return None

        attributes = record.get("attributes") or {}
        result = Refresh()
        result.fields += await self._fill_work(ctype, cid, work, attributes)
        result.fields += await self._fill_genre(ctype, cid, work, record)

        episodes = await self._episodes(ctype, cid)
        result.fields += await self._fill_episodes(episodes)
        result.images += await self._store_cover(episodes, attributes)

        crologger.info(
            "Library: refreshed %s (%s fields, %s images)",
            cid,
            result.fields,
            result.images,
        )

        return result

    async def _api_uuid(self, ctype: str, cid: str) -> Optional[str]:
        """
        Which Czech Radio work to ask about: its own id, or the one its page names.

        A work adopted from disk is keyed by a hash of its folder; if somebody
        added the mujrozhlas.cz page it came from, that page says which work it
        is. The uuid is remembered on the link, so a page is scraped once.
        """
        if api_id(cid):
            return cid

        link = await self.repository.get_work_link(cid)
        if link is None:
            return None

        if api_id(link.resolved_uuid):
            return link.resolved_uuid

        resolved = await self._resolve(ctype, link.source_url)
        if resolved is None:
            return None

        link.resolved_uuid = resolved
        await self.repository.save_work_link(link)
        crologger.info("Library: %s resolved to %s", link.source_url, resolved)

        return resolved

    async def _resolve(self, ctype: str, url: str) -> Optional[str]:
        """The uuid behind a mujrozhlas.cz page, scraped off the page itself."""
        # The work's own kind first: a page answers several of these scrapers,
        # and the one that matches tells us which entity the uuid belongs to.
        fetches = (
            (self.client.get_series_id, self.client.get_show_uuid)
            if ctype == "series"
            else (self.client.get_show_uuid, self.client.get_series_id)
        )

        for fetch in fetches:
            try:
                uuid = await asyncio.to_thread(fetch, url)
            except Exception as error:  # a page that is not that kind of work
                crologger.warning("Could not read %s: %s", url, error)
                continue

            if uuid:
                return str(uuid)

        return None

    async def _record(self, uuid: str) -> Optional[dict[str, Any]]:
        """
        The API's record behind a uuid, whatever kind it is.

        A uuid does not say what it is - and a library row may well be of another
        kind than the API's record: a folder adopted from disk often looks like a
        show while the page behind it is a one-off episode (or the other way
        round). Asking the API about just the row's kind answered "no such
        entity" for those, so every kind is asked; the first answer wins.
        """
        for fetch_name in ENTITY_FETCHES:
            fetch = getattr(self.client, fetch_name)
            try:
                data = await asyncio.to_thread(fetch, uuid)
            except Exception as error:  # this is not the kind of entity it is
                crologger.warning("Not a %s: %s (%s)", fetch_name, uuid, error)
                continue

            record = (data or {}).get("data")

            if isinstance(record, Mapping) and record.get("attributes"):
                return dict(record)

        return None

    async def _fill_work(
        self,
        ctype: str,
        cid: str,
        work: Any,
        attributes: Mapping[str, Any],
    ) -> int:
        """Fills the work's own missing title/description."""
        changes = _missing(work, attributes, ("title", "description"))

        if changes:
            if ctype == "series":
                await self.repository.update_series(cid, changes)
            else:
                await self.repository.update_show(cid, changes)

        return len(changes)

    async def _fill_genre(
        self, ctype: str, cid: str, work: Any, record: Mapping[str, Any]
    ) -> int:
        """
        The genre the API lists for the work, when it has none yet.

        Genres hang off the work's relationships rather than its attributes, so
        they travel beside them; a genre somebody typed by hand wins.
        """
        if getattr(work, "genre", None):
            return 0

        genre = extract_genre({"data": dict(record)})
        if not genre:
            return 0

        if ctype == "series":
            await self.repository.update_series(cid, {"genre": genre})
        else:
            await self.repository.update_show(cid, {"genre": genre})

        return 1

    async def _fill_episodes(self, episodes: list[Episode]) -> int:
        """Fills what each part is missing, one API call per part that needs one."""
        filled = 0

        for episode in episodes:
            if not api_id(episode.uuid) or not _part_needs_data(episode):
                continue

            try:
                data = await asyncio.to_thread(
                    self.client.get_episode_data, episode.uuid
                )
            except Exception as error:
                crologger.error("Refresh failed for part %s: %s", episode.uuid, error)
                continue

            attributes = (data or {}).get("data", {}).get("attributes") or {}
            changes = _missing(episode, attributes, EPISODE_FIELDS)

            if attributes.get("since") and not episode.broadcast_at:
                changes["broadcast_at"] = to_naive_utc(parse_since(attributes["since"]))

            if changes:
                await self.repository.update_episode(episode.uuid, changes)
                filled += len(changes)

        return filled

    async def _store_cover(
        self, episodes: list[Episode], attributes: Mapping[str, Any]
    ) -> int:
        """
        Stores the work's own cover for the parts that have none.

        One file per work, like the download does: the parts of a work share the
        image the API reports for it.
        """
        url = extract_asset_url(dict(attributes))
        missing = [episode for episode in episodes if not episode.image_path]

        if not url or not missing:
            return 0

        folder = Path(episodes[0].local_path).parent
        target = cover_path(url, folder)
        cover = target if target.exists() else await fetch_cover(url, folder)

        if cover is None:
            return 0

        await self.repository.set_artwork([episode.uuid for episode in missing], cover)

        return 1

    async def _episodes(self, ctype: str, cid: str) -> list[Episode]:
        """The stored parts of a work, in the order the library keeps them."""
        if ctype == "series":
            return list(await self.repository.get_episodes_by_series(cid))

        return list(await self.repository.get_episodes_by_show(cid))


def _missing(
    row: Any, attributes: Mapping[str, Any], fields: tuple[str, ...]
) -> dict[str, Any]:
    """The fields the row does not have yet but the API can provide."""
    changes: dict[str, Any] = {}

    for field in fields:
        if getattr(row, field, None):
            continue

        value = attributes.get(_api_key(field))
        if value in (None, ""):
            continue

        if field == "description":
            value = remove_html_tags(str(value))

        changes[field] = value

    return changes


def _part_needs_data(episode: Episode) -> bool:
    """Whether asking the API about this part could add anything."""
    return not (episode.author and episode.description and episode.duration)


#: The API's name for the columns we fill in.
API_KEYS = {"short_title": "shortTitle"}


def _api_key(field: str) -> str:
    return API_KEYS.get(field, field)
