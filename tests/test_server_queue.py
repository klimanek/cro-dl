import unittest
from pathlib import Path
from typing import Optional

from crodl.library.models import Episode
from crodl.library.service import LibraryItem
from crodl.server.queue import queue_items
from crodl.settings import DOWNLOAD_PATH


def work() -> LibraryItem:
    return LibraryItem(type="series", id="s1", title="Seriál", from_api=True)


def episode(uuid: str, title: str, part: Optional[int], name: Optional[str]) -> Episode:
    # Only files inside the download directory are servable, so the queue only
    # ever holds those (see `media_url`).
    local_path = str(DOWNLOAD_PATH / "Seriály" / "S" / name) if name else None

    return Episode(
        uuid=uuid,
        title=title,
        part=part,
        local_path=local_path,
        audio_format="mp3",
    )


class TestQueueItems(unittest.TestCase):
    """What "Přidat do fronty" puts into the player's queue."""

    def test_parts_come_back_in_order_and_name_their_work(self):
        items = queue_items(
            work(),
            [
                episode("p1", "Díl", 1, "1 - Díl.mp3"),
                episode("p2", "Díl", 2, "2 - Díl.mp3"),
            ],
        )

        self.assertEqual([item["title"] for item in items], ["1. Díl", "2. Díl"])
        self.assertEqual(items[0]["work"], "Seriál")
        self.assertTrue(items[0]["src"].startswith("/library/"))

    def test_a_part_without_a_file_is_not_queued(self):
        self.assertEqual(queue_items(work(), [episode("p1", "Díl", 1, None)]), [])

    def test_a_file_outside_the_library_is_not_queued(self):
        outside = Episode(
            uuid="p1",
            title="Díl",
            part=1,
            local_path=str(Path("/tmp") / "jinde.mp3"),
            audio_format="mp3",
        )

        self.assertEqual(queue_items(work(), [outside]), [])

    def test_a_work_without_parts_is_empty(self):
        self.assertEqual(queue_items(work(), []), [])
        self.assertEqual(queue_items(None, []), [])


if __name__ == "__main__":
    unittest.main()
