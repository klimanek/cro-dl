from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from crodl.tools.api_client import CroAPIClient


@dataclass
class Content(ABC):
    url: Optional[str] = None
    uuid: Optional[str] = None
    title: Optional[str] = None
    client: CroAPIClient = field(default_factory=CroAPIClient, repr=False)

    @abstractmethod
    def already_exists(self) -> bool:
        pass

    @abstractmethod
    async def download(self) -> None:
        pass
