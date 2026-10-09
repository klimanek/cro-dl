from dataclasses import dataclass, field
from typing import Optional

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


def extract_asset_url(attributes: dict) -> Optional[str]:
    """
    URL of the artwork the API reports for an episode, series or show.

    The content API nests it in an `asset` object - `{"url": ..., "width": ...,
    "credit": {...}, "inherited": true}` - so `str()` of that value is the
    dict's repr, not a URL. A plain URL string is accepted as well, because
    some payloads (and old fixtures) carry one.
    """
    asset = attributes.get("asset")

    if isinstance(asset, dict):
        url = asset.get("url")
        return str(url) if url else None

    return str(asset) if asset else None


def extract_genre(payload: dict) -> Optional[str]:
    """
    The first genre the API lists for a work, if it lists any.

    Genres hang off the work, not off its parts, and arrive as a relationship
    (`data.relationships.genres.data[].attributes.title`) - "Horor", "Komedie"
    and the like, which is what a player wants in a tag.
    """
    relationships = (payload or {}).get("data", {}).get("relationships", {})
    genres = relationships.get("genres", {}).get("data") or []

    for genre in genres:
        title = (genre.get("attributes") or {}).get("title")
        if title:
            return str(title)

    return None


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
