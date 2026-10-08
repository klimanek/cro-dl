"""Watching the library for parts the Czech Radio has released since.

A series publishes an episode a day or a week, so what is on disk is a snapshot:
this asks the content API what a work has now and compares it with the parts the
library holds. The answer is remembered (`UpdateCheck`) so a badge survives the
next page - the check itself is one request per work.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from crodl.data.attributes import extract_asset_url
from crodl.library.models import Episode, UpdateCheck
from crodl.library.refresh import api_id
from crodl.library.repository import SqliteLibraryRepository
from crodl.settings import API_SERVER
from crodl.tools.api_client import CroAPIClient
from crodl.tools.logger import crologger


@dataclass(frozen=True)
class NewPart:
    """One part the API has and the library does not."""

    uuid: str
    title: str
    part: Optional[int] = None
    #: The image the API reports for this part (a work's parts share one).
    asset_url: Optional[str] = None


def episodes_url(ctype: str, cid: str) -> Optional[str]:
    """Where the API lists the parts of a work."""
    if ctype == "series":
        return f"{API_SERVER}/serials/{cid}/episodes"
    if ctype == "show":
        return f"{API_SERVER}/shows/{cid}/episodes"

    return None


class LibraryUpdates:
    """Looks for new parts, and answers what one work is missing."""

    def __init__(
        self,
        repository: Optional[SqliteLibraryRepository] = None,
        client: Optional[CroAPIClient] = None,
    ) -> None:
        self.repository = repository or SqliteLibraryRepository()
        self.client = client or CroAPIClient()

    async def check_all(self) -> int:
        """
        Looks at every work the library holds; returns how many gained parts.

        One request per work, so a library of a few dozen works is a few dozen
        requests - the price of noticing a new episode without the user asking.
        """
        checked = 0

        for ctype, cid in await self._works():
            check = await self.check_work(ctype, cid)

            if check is not None and check.missing:
                checked += 1

        crologger.info("New-part check: %s works have something new", checked)
        return checked

    async def check_work(self, ctype: str, cid: str) -> Optional[UpdateCheck]:
        """
        Compares one work with the API and remembers the difference.

        Returns None for a work the API cannot know (a folder adopted from disk).
        """
        missing = await self.missing_parts(ctype, cid)

        if missing is None:
            return None

        check = UpdateCheck(
            collection_id=cid, collection_type=ctype, missing=len(missing)
        )

        return await self.repository.save_update_check(check)

    async def missing_parts(self, ctype: str, cid: str) -> Optional[list[NewPart]]:
        """
        The parts the API lists that the library does not have.

        None when there is nothing to ask about (no Czech Radio id, or an API
        that is away).
        """
        url = episodes_url(ctype, cid)
        if not api_id(cid) or url is None:
            return None

        data = await self._fetch(url)
        if data is None:
            return None

        stored = await self._stored_uuids(ctype, cid)
        parts = []

        for episode in data:
            uuid = episode.get("id")
            if not uuid or uuid in stored:
                continue

            attributes = episode.get("attributes", {})
            parts.append(
                NewPart(
                    uuid=str(uuid),
                    title=str(attributes.get("title", "Unknown")),
                    part=attributes.get("part"),
                    asset_url=extract_asset_url(attributes),
                )
            )

        return parts

    async def _fetch(self, url: str) -> Optional[list[Mapping[str, Any]]]:
        """The API's episode list, fetched off the event loop."""
        try:
            payload = await asyncio.to_thread(self.client.get_related_data, url)
        except Exception as error:  # the API is the network: it may be away
            crologger.error("New-part check failed for %s: %s", url, error)
            return None

        data = (payload or {}).get("data")

        return data if isinstance(data, list) else None

    async def _stored_uuids(self, ctype: str, cid: str) -> set[str]:
        """The parts of a work the library already has."""
        episodes: list[Episode] = list(
            await (
                self.repository.get_episodes_by_series(cid)
                if ctype == "series"
                else self.repository.get_episodes_by_show(cid)
            )
        )

        return {episode.uuid for episode in episodes}

    async def _works(self) -> list[tuple[str, str]]:
        """Every work that could have a counterpart in the API."""
        series = await self.repository.get_all_series()
        shows = await self.repository.get_all_shows()

        return [("series", row.uuid) for row in series] + [
            ("show", row.uuid) for row in shows
        ]
