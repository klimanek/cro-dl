"""The release description a tag gets: its CHANGELOG.md section."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "scripts" / "release_notes.py"
)
assert SPEC is not None and SPEC.loader is not None
release_notes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [2.1.2] - 2026-11-24

### Fixed
- Something.

## [2.1.1] - 2026-11-24

### Fixed
- Older.
"""


class TestTheSection(unittest.TestCase):
    def test_it_takes_only_that_version(self):
        self.assertEqual(
            release_notes.section(CHANGELOG, "2.1.2"), "### Fixed\n- Something."
        )

    def test_a_missing_version_is_an_error(self):
        with self.assertRaisesRegex(ValueError, r"no ## \[9\.9\.9\] section"):
            release_notes.section(CHANGELOG, "9.9.9")

    def test_an_empty_section_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "is empty"):
            release_notes.section("## [1.0] - x\n\n## [0.9] - y\n- x\n", "1.0")


class TestTheCommand(unittest.TestCase):
    def test_it_writes_the_section_for_the_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
            previous = Path.cwd()
            os.chdir(folder)

            try:
                release_notes.main(["v2.1.2", "notes.md"])
            finally:
                os.chdir(previous)

            self.assertEqual(
                (folder / "notes.md").read_text(encoding="utf-8"),
                "### Fixed\n- Something.\n",
            )

    def test_wrong_arguments_are_a_usage_error(self):
        with self.assertRaises(SystemExit):
            release_notes.main(["v2.1.2"])


if __name__ == "__main__":
    unittest.main()
