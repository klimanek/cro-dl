"""The parts of a work as the bottom player's queue wants them."""

from typing import Any, Optional, Sequence

from crodl.library.models import Episode
from crodl.library.service import LibraryItem
from crodl.server.format import media_url
from crodl.streams.utils import title_without_part


def queue_items(
    content: Optional[LibraryItem], episodes: Optional[Sequence[Episode]]
) -> list[dict[str, Any]]:
    """
    Queue entries for one work, in playing order, one per part that has a file.

    `src` is what the browser fetches, `title` what the player shows (without the
    part number - the page puts that beside it) and `part` the number itself, so
    a page can say "3. díl" without it appearing three times over.
    """
    if content is None or not episodes:
        return []

    items: list[dict[str, Any]] = []

    for episode in episodes:
        src = media_url(episode.local_path)
        if not src:
            continue

        items.append(
            {
                "src": src,
                "title": title_without_part(episode.title, episode.part),
                "part": episode.part,
                "work": content.title,
            }
        )

    return items
