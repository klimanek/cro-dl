from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

from crodl.tools.api_client import CroAPIClient
from crodl.settings import AudioFormat

if TYPE_CHECKING:
    from crodl.program.audiowork import AudioWork

# Called once a work has been written to disk: (work, local_path).
DownloadedHook = Callable[["AudioWork", Path], Awaitable[None]]


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

    @abstractmethod
    async def download(
        self,
        audio_format: Optional[AudioFormat] = None,
        progress: Any = None,
        task_id: Any = None,
        on_downloaded: Optional[DownloadedHook] = None,
    ) -> None:
        """
        Downloads the content.

        `on_downloaded` is the core's only way out to a storage layer: the
        core itself knows nothing about a database (see `crodl.library`).
        """
        pass
