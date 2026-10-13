import tempfile
import unittest
from pathlib import Path
from typing import Optional

from crodl.server.browse import listing


class TestFolderBrowser(unittest.TestCase):
    """Choosing the folder to import, instead of typing its path."""

    def test_it_lists_the_folders_inside_a_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Beta").mkdir()
            (root / "alpha").mkdir()
            (root / ".hidden").mkdir()
            (root / "a-file.txt").write_text("x", encoding="utf-8")

            seen = listing(str(root))

            # Only folders, alphabetically and case-insensitively.
            self.assertEqual([child.name for child in seen.children], ["alpha", "Beta"])
            self.assertIsNone(seen.error)
            self.assertEqual(seen.folder, root.resolve())

    def test_no_path_starts_at_home(self):
        self.assertEqual(listing(None).folder, Path.home().resolve())

    def test_a_folder_that_is_not_there_says_so(self):
        # An unplugged disk is talked about, not raised: the page must render.
        seen = listing("/nonexistent/wherever")

        self.assertIsNotNone(seen.error)
        self.assertEqual(seen.children, [])

    def test_a_file_is_not_a_folder_to_browse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path: Path = Path(tmp) / "note.txt"
            path.write_text("x", encoding="utf-8")

            self.assertIsNotNone(listing(str(path)).error)

    def test_it_offers_the_way_back_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = listing(str(Path(tmp)))

            # The breadcrumb reads from the filesystem root inwards; walking up is
            # how the browser gets from $HOME to /Volumes.
            self.assertEqual(seen.parents[0], Path("/"))
            self.assertEqual(seen.parents[-1], Path(tmp).resolve().parent)

    def test_an_empty_folder_is_still_a_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty: Optional[str] = str(Path(tmp) / "prazdna")
            Path(empty).mkdir()

            seen = listing(empty)

            self.assertEqual(seen.children, [])
            self.assertIsNone(seen.error)


if __name__ == "__main__":
    unittest.main()
