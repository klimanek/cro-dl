from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Content(ABC):
    url: str
    title: str = field(init=False)

    @abstractmethod
    def already_exists(self) -> bool:
        pass

    @abstractmethod
    async def download(self) -> None:
        pass
