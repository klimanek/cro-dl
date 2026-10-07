import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crodl.program.series import Series


class SeriesTestCase(unittest.TestCase):
    """Builds a loaded Series with a mocked API client, so no network is involved."""

    total_parts = 3

    def make_series(self, download_dir: Path, total_parts: int | None = None) -> Series:
        client = mock.Mock()
        client.get_series_id.return_value = "series-uuid"
        client.get_series_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Test Series",
                    "totalParts": self.total_parts
                    if total_parts is None
                    else total_parts,
                    "playable": True,
                }
            }
        }
        series = Series(
            url="https://example.com/series",
            download_dir=download_dir,
            client=client,
        )
        asyncio.run(series.load())
        return series

    def write_file(self, directory: Path, name: str) -> None:
        (directory / name).write_text("x", encoding="utf-8")


class TestSeriesDownloadedParts(SeriesTestCase):
    def test_counts_real_sanitized_file_names(self):
        # Regression: files are written as "3 - Díl.mp3" (sanitize_filename
        # expands the dash), while the old check looked for the prefix "3-"
        # and therefore always counted 0.
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            for part in (1, 2, 3):
                self.write_file(Path(tmp), f"{part} - Díl {part}.aac")

            self.assertEqual(series.downloaded_parts, 3)
            self.assertTrue(series.already_exists())

    def test_missing_part_is_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            for part in (1, 3):
                self.write_file(Path(tmp), f"{part} - Díl {part}.mp3")

            self.assertEqual(series.downloaded_parts, 2)
            self.assertFalse(series.already_exists())

    def test_compact_separator_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            self.write_file(Path(tmp), "1-Díl.mp3")
            self.write_file(Path(tmp), "2-Díl.m4a")
            self.write_file(Path(tmp), "3-Díl.mp3")

            self.assertEqual(series.downloaded_parts, 3)

    def test_ignores_non_audio_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            self.write_file(Path(tmp), "1 - Díl.txt")

            self.assertEqual(series.downloaded_parts, 0)

    def test_ignores_parts_outside_the_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            self.write_file(Path(tmp), "9 - Díl.mp3")

            self.assertEqual(series.downloaded_parts, 0)

    def test_series_marker_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            self.write_file(Path(tmp), ".series")

            self.assertEqual(series.downloaded_parts, 0)

    def test_missing_directory_counts_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp) / "does-not-exist")

            self.assertEqual(series.downloaded_parts, 0)
            self.assertFalse(series.already_exists())

    def test_duplicate_parts_are_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))
            self.write_file(Path(tmp), "1 - Díl.mp3")
            self.write_file(Path(tmp), "1 - Díl.aac")

            self.assertEqual(series.downloaded_parts, 1)


class TestSeriesEpisodeCaching(SeriesTestCase):
    def test_episodes_are_fetched_only_once(self):
        # Regression (REFACTORING_TODO item 5): `episodes_data` used to hit the
        # API on every access (audio_formats, list_all_series_episodes, ...).
        with tempfile.TemporaryDirectory() as tmp:
            series = self.make_series(Path(tmp))

            series.episodes_data
            series.episodes_data
            series.list_all_series_episodes()

            series.client.get_related_data.assert_called_once()


if __name__ == "__main__":
    unittest.main()
