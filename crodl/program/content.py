from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any

from crodl.tools.api_client import CroAPIClient
from crodl.settings import AudioFormat


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
    ) -> None:
        pass
