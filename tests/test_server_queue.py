import shutil
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
    # Only files inside the download directory are servable, and only files that
    # are there: the queue is built on real paths (see `media_url`).
    if not name:
        return Episode(
            uuid=uuid, title=title, part=part, local_path=None, audio_format="mp3"
        )

    path = DOWNLOAD_PATH / "Seriály" / "S" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")

    return Episode(
        uuid=uuid,
        title=title,
        part=part,
        local_path=str(path),
        audio_format="mp3",
    )


class TestQueueItems(unittest.TestCase):
    """What "Přidat do fronty" puts into the player's queue."""

    def tearDown(self):
        shutil.rmtree(DOWNLOAD_PATH / "Seriály" / "S", ignore_errors=True)

    def test_parts_come_back_in_order_and_name_their_work(self):
        items = queue_items(
            work(),
            [
                episode("p1", "1-Díl", 1, "1 - Díl.mp3"),
                episode("p2", "2-Díl", 2, "2 - Díl.mp3"),
            ],
        )

        # The part is data of its own: the title leaves the number out, and the
        # page shows "1." and "1. díl" around it. A stored title carries the "1-"
        # prefix (files sort by it), which is what made the queue read
        # "1. 1. 1-Jack Black: Nemáte šanci".
        self.assertEqual([item["title"] for item in items], ["Díl", "Díl"])
        self.assertEqual([item["part"] for item in items], [1, 2])
        self.assertEqual(items[0]["work"], "Seriál")
        self.assertTrue(items[0]["src"].startswith("/library/"))

    def test_a_title_without_a_part_number_is_left_alone(self):
        items = queue_items(
            work(), [episode("p1", "Medvěd Čokoláda", None, "Medvěd Čokoláda.mp3")]
        )

        self.assertEqual([item["title"] for item in items], ["Medvěd Čokoláda"])
        self.assertIsNone(items[0]["part"])

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
