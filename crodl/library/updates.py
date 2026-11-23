"""Watching the library for parts the Czech Radio has released since.

A series publishes an episode a day or a week, so what is on disk is a snapshot:
this asks the content API what a work has now and compares it with the parts the
library holds. The answer is remembered (`UpdateCheck`) so a badge survives the
next page - the check itself is one request per work, so works that cannot have
anything new (a one-off episode, a work whose parts are all here) are left out
(`worth_checking`).
"""

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from crodl.data.attributes import extract_asset_url
from crodl.library.models import Episode, UpdateCheck
from crodl.library.refresh import api_id
from crodl.library.repository import SqliteLibraryRepository
from crodl.settings import API_SERVER
from crodl.tools.api_client import CroAPIClient
from crodl.tools.logger import crologger

#: A part the library lacks is in one of three situations.
AVAILABLE = "available"  # aired and still streamable: fetch it
UPCOMING = "upcoming"  # announced, not aired yet: nothing to fetch
EXPIRED = "expired"  # aired, but the stream is gone for good


@dataclass(frozen=True)
class NewPart:
    """One part the API has and the library does not."""

    uuid: str
    title: str
    part: Optional[int] = None
    #: The image the API reports for this part (a work's parts share one).
    asset_url: Optional[str] = None
    #: What kind of "missing" this is (see `part_state`).
    state: str = AVAILABLE

    @property
    def fetchable(self) -> bool:
        return self.state == AVAILABLE


def part_state(attributes: Mapping[str, Any], now: Optional[datetime] = None) -> str:
    """
    Whether a part the library lacks can still be fetched, or when it will be.

    The API hands out `since` (when the part airs) and `till`, but `till` is the
    *broadcast* end, not how long the stream stays: parts that aired weeks ago
    still carry a `till` in the past while their streams live on. What actually
    expires is the audio: a part with no `audioLinks` cannot be downloaded any
    more - the case that made a library report "2 nové díly" for two parts that
    were long gone.
    """
    moment = now or datetime.now(timezone.utc)
    since = _moment(attributes.get("since"))

    if since is not None and since > moment:
        return UPCOMING

    if not attributes.get("audioLinks"):
        return EXPIRED

    return AVAILABLE


def _moment(value: Any) -> Optional[datetime]:
    """An API timestamp as an aware datetime, if it parses."""
    if not value:
        return None

    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None

    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def count_states(parts: list[NewPart]) -> Counter:
    """How many of the missing parts are available, upcoming, or expired."""
    return Counter(part.state for part in parts)


def worth_checking(
    parts: int,
    check: Optional[UpdateCheck],
    *,
    one_off: bool = False,
    include_complete: bool = False,
) -> bool:
    """
    Whether asking the API about a work can still tell the library anything.

    A one-off episode is stored as a show of its own - its uuid *is* the
    episode's (`LibraryService._own_collection`) - so it has exactly one part,
    can never gain another, and has no show behind it for the API to answer
    about. A work whose last check found nothing missing is complete, and a work
    with one part in total has nothing to compare.

    `parts` is what the library holds; the last check's missing counts are added,
    so the number is the last known total and a series with one part downloaded
    of three is still checked. `include_complete` is the manual "Zkontrolovat
    nové díly": it deliberately asks about complete works too, which is how a new
    episode of a finished series is discovered.
    """
    if check is None:
        # Nothing is known about this work yet: ask once, unless it is a one-off.
        return not one_off

    total = parts + check.available + check.upcoming + check.expired
    if total <= 1:
        return False

    if include_complete:
        return True

    return bool(check.available or check.upcoming or check.expired)


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

    async def check_all(self, include_complete: bool = False) -> int:
        """
        Looks at the works the library holds; returns how many gained a part.

        One request per work, so a library of a few dozen works is a few dozen
        requests - the price of noticing a new episode without the user asking.
        A work that cannot have anything new is left out (`worth_checking`), so
        finished works are not asked about every cycle. `include_complete` is the
        manual check, which does ask about them.

        Only parts that can still be fetched count as news here; what expired or
        has not aired yet lives in the badges, not in "nové díly".
        """
        checks = {
            check.collection_id: check
            for check in await self.repository.get_update_checks()
        }
        stored = await self._stored_parts()
        checked = 0
        skipped = 0

        for ctype, cid in await self._works():
            parts = stored.get((ctype, cid), [])
            if not worth_checking(
                len(parts),
                checks.get(cid),
                one_off=ctype == "show" and parts == [cid],
                include_complete=include_complete,
            ):
                skipped += 1
                continue

            try:
                check = await self.check_work(ctype, cid)
            except Exception as error:
                # One work the API (or the database) refuses must not stop the
                # rest of the library; the next run picks it up again.
                crologger.error("Could not check %s: %s", cid, error)
                continue

            if check is not None and check.available:
                checked += 1

        crologger.info(
            "New-part check: %s works have new parts, %s works skipped",
            checked,
            skipped,
        )
        return checked

    async def check_work(self, ctype: str, cid: str) -> Optional[UpdateCheck]:
        """
        Compares one work with the API and remembers the difference.

        Returns None for a work the API cannot know (a folder adopted from disk).
        """
        missing = await self.missing_parts(ctype, cid)

        if missing is None:
            return None

        counted = count_states(missing)
        check = UpdateCheck(
            collection_id=cid,
            collection_type=ctype,
            available=counted[AVAILABLE],
            upcoming=counted[UPCOMING],
            expired=counted[EXPIRED],
        )

        return await self.repository.save_update_check(check)

    async def missing_parts(self, ctype: str, cid: str) -> Optional[list[NewPart]]:
        """
        The parts the API lists that the library does not have.

        Each one says whether it can still be fetched, will be aired, or is gone
        (see `part_state`). None when there is nothing to ask about (no Czech
        Radio id, or an API that is away).
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
                    state=part_state(attributes),
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

    async def _stored_parts(self) -> dict[tuple[str, str], list[str]]:
        """The uuids of the parts the library holds, grouped by their work."""
        grouped: dict[tuple[str, str], list[str]] = {}

        for episode in await self.repository.get_all_episodes():
            if episode.series_id:
                key = ("series", episode.series_id)
            elif episode.show_id:
                key = ("show", episode.show_id)
            else:
                continue

            grouped.setdefault(key, []).append(episode.uuid)

        return grouped
