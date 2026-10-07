from dataclasses import dataclass, field
from typing import Dict, Any

from crodl.streams.utils import get_audio_link_of_preferred_format


@dataclass
class Attributes:
    title: str
    active: bool
    aired: bool
    description: str
    short_description: str


@dataclass
class Data:
    show_type: str
    uuid: str
    attributes: Attributes


def extract_episode_info(episode: dict) -> dict:
    """
    Maps one episode dict (as returned by the API) to a plain info dict.

    Shared by all content collections (Series, Show) so that the episode
    mapping logic lives in a single place.
    """
    attrs = episode.get("attributes", {})
    return {
        "uuid": episode.get("id"),
        "title": attrs.get("title", ""),
        "url": get_audio_link_of_preferred_format(attrs),
        "since": attrs.get("since"),
        "part": attrs.get("part"),
    }


@dataclass
class Episodes:
    show_title: str
    show_id: str
    json_data: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if not self.json_data:
            self.data = []
            self.count = 0
            return

        self.data = self.json_data.get("data", [])
        self.count = self.json_data.get("meta", {}).get("count", 0)

    @property
    def info(self) -> list[dict]:
        return [extract_episode_info(_data) for _data in self.data]

    def __str__(self):
        return f"<Episodes of {self.show_title}>"

    def __repr__(self):
        return f"<Episodes of {self.show_title}>"
