from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(init=False)
class Content(ABC):
    url: str
    uuid: str = field(init=False)
    title: str = field(init=False)

    @abstractmethod
    def already_exists(self) -> bool:
        pass

    @abstractmethod
    async def download(self) -> None:
        pass
