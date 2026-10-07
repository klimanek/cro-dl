from dataclasses import dataclass, field

from crodl.streams.utils import get_audio_link_of_preferred_format, title_with_part


@dataclass(frozen=True)
class Attributes:
    title: str
    active: bool
    aired: bool
    description: str
    short_description: str


@dataclass(frozen=True)
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
    """
    A collection of episodes, shared by Series and Show.

    It owns the single episode mapping used for downloading: raw API entries
    are turned into flat info dicts whose `title` already carries the
    "<part>-<title>" file name.

    Deliberately not `frozen`: it holds the raw, mutable list of API entries,
    so freezing it would only generate a `__hash__` that fails at runtime.
    """

    title: str = ""
    uuid: str = ""
    data: list[dict] = field(default_factory=list, repr=False)
    count: int = 0

    @property
    def info(self) -> list[dict]:
        items = []
        for episode in self.data:
            info = extract_episode_info(episode)
            info["title"] = title_with_part(
                str(info["title"] or "Unknown"), info["part"]
            )
            items.append(info)
        return items

    def __str__(self) -> str:
        return f"<Episodes of {self.title}>"

    def __repr__(self) -> str:
        return f"<Episodes of {self.title}>"
