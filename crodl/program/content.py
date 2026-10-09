from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

from crodl.data.attributes import extract_asset_url
from crodl.tools.api_client import CroAPIClient
from crodl.settings import AudioFormat

if TYPE_CHECKING:
    from crodl.program.audiowork import AudioWork


@dataclass(frozen=True)
class Collection:
    """
    The show or series an episode belongs to.

    Multi-part works are downloaded episode by episode, so each part has to
    carry what ties it to its collection: the library links the episode to this
    work and, when `shared_asset_url` is set, stores one cover for all parts
    instead of fetching the same image again for every one of them.
    """

    uuid: str
    # "show" or "series" - what the library stores this collection as.
    type: str
    title: str
    description: Optional[str] = None
    # Artwork every part of this collection reports, if they share one.
    shared_asset_url: Optional[str] = None
    #: The genre the API lists for the work ("Horor", "Komedie", …), if any.
    genre: Optional[str] = None


def shared_artwork_url(episodes: list[dict]) -> Optional[str]:
    """
    The artwork URL that all parts of a collection report, if they have one.

    The parts of a single work (the chapters of a reading, say) inherit one
    image from their series, while a collection of separate works gives every
    part its own - comparing the URLs tells the two apart. Returns None for a
    single-part work and for parts with distinct (or no) images.
    """
    if len(episodes) < 2:
        return None

    urls = {
        url
        for url in (
            extract_asset_url(episode.get("attributes", {})) for episode in episodes
        )
        if url
    }

    return urls.pop() if len(urls) == 1 else None


# Called once a work has been written to disk: (work, local_path, collection).
DownloadedHook = Callable[["AudioWork", Path, Optional[Collection]], Awaitable[None]]


@dataclass
class Content(ABC):
    url: Optional[str] = None
    uuid: Optional[str] = None
    title: str = "Unknown"
    client: CroAPIClient = field(default_factory=CroAPIClient, repr=False)
    loaded: bool = field(default=False, repr=False)

    @abstractmethod
    async def load(self) -> None:
        """
        Fetches the API data this content needs. Must be idempotent.

        Constructors stay free of I/O, so anything that reads API-derived
        fields has to call (and await) this first.
        """
        pass

    @abstractmethod
    def already_exists(self) -> bool:
        pass

    @property
    def parent(self) -> Optional[tuple[str, str]]:
        """
        The work this content belongs to, as `(kind, uuid)`, if the API names one.

        A one-off episode (a play inside a magazine show) is downloaded as a work
        of its own, but the record fetched for it names the show or serial it was
        aired in - that is what the library files it under. A series or a show is
        its own work and has no parent here.
        """
        return None

    @abstractmethod
    async def download(
        self,
        audio_format: Optional[AudioFormat] = None,
        progress: Any = None,
        task_id: Any = None,
        on_downloaded: Optional[DownloadedHook] = None,
        collection: Optional[Collection] = None,
    ) -> None:
        """
        Downloads the content.

        `on_downloaded` is the core's only way out to a storage layer: the
        core itself knows nothing about a database (see `crodl.library`).
        `collection` is what the storage layer needs to tie a single part to
        the work it belongs to; a standalone work passes None.
        """
        pass
