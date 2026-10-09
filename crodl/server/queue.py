"""The parts of a work as the bottom player's queue wants them."""

from typing import Optional, Sequence

from crodl.library.models import Episode
from crodl.library.service import LibraryItem
from crodl.server.format import media_url


def queue_items(
    content: Optional[LibraryItem], episodes: Optional[Sequence[Episode]]
) -> list[dict[str, str]]:
    """
    Queue entries for one work, in playing order, one per part that has a file.

    `src` is what the browser fetches, `title` what the player shows and `work`
    what it came from - enough for the queue to name a part the page it was added
    from is no longer showing.
    """
    if content is None or not episodes:
        return []

    items: list[dict[str, str]] = []

    for episode in episodes:
        src = media_url(episode.local_path)
        if not src:
            continue

        title = f"{episode.part}. {episode.title}" if episode.part else episode.title
        items.append({"src": src, "title": title, "work": content.title})

    return items
