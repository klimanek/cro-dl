import os
import unittest
import tempfile
from pathlib import Path

from crodl.settings import AudioFormat
from crodl.streams.utils import (
    day_month_year,
    get_m4a_url,
    audio_segment_sort,
    get_preferred_audio_format,
    partial_sums,
    process_audiowork_title,
    simplify_audio_name,
    create_dir_if_does_not_exist,
    title_with_part,
)


class TestGetM4aUrl(unittest.TestCase):
    def test_manifest_mpd(self):
        audio_link = "https://example.com/manifest.mpd"
        expected_output = "https://example.com"
        self.assertEqual(get_m4a_url(audio_link), expected_output)

    def test_playlist_m3u8(self):
        audio_link = "https://example.com/playlist.m3u8"
        expected_output = "https://example.com"
        self.assertEqual(get_m4a_url(audio_link), expected_output)

    def test_neither_pattern(self):
        audio_link = "https://example.com/some_other_url"
        with self.assertRaises(ValueError):
            get_m4a_url(audio_link)

    def test_empty_audio_link(self):
        audio_link = ""
        with self.assertRaises(ValueError):
            get_m4a_url(audio_link)


class TestPartialSums(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(partial_sums([]), [])

    def test_single_element_list(self):
        self.assertEqual(partial_sums([5]), [5])

    def test_multiple_elements_list(self):
        self.assertEqual(partial_sums([6, 5, 6, 5, 6, 3]), [6, 11, 17, 22, 28, 31])


class TestGetPreferredAudioFormat(unittest.TestCase):
    def test_preferred_audio_format_first_variant(self):
        audio_variants = ["mp3", "hls", "dash"]
        result = get_preferred_audio_format(audio_variants)
        self.assertEqual(result, AudioFormat.MP3)

    def test_preferred_audio_format_last_variant(self):
        audio_variants = ["wma", "ogg", "dash"]
        result = get_preferred_audio_format(audio_variants)
        self.assertEqual(result, AudioFormat.DASH)

    def test_no_matching_audio_format(self):
        audio_variants = ["wma", "ogg", "flac"]
        result = get_preferred_audio_format(audio_variants)
        self.assertIsNone(result)


class TestProcessAudioworkTitle(unittest.TestCase):
    def test_title_contains_colon(self):
        title = "Sample: Title"
        processed_title = process_audiowork_title(title)
        self.assertEqual(processed_title, "Sample - Title")

    def test_title_does_not_contain_colon(self):
        title = "Sample Title"
        processed_title = process_audiowork_title(title)
        self.assertEqual(processed_title, "Sample Title")

    def test_title_contains_colon_and_prefix(self):
        title = "Sample: Title"
        processed_title = process_audiowork_title(title, prefix="01")
        self.assertEqual(processed_title, "01 - Sample - Title")


class TestAudioSegmentSort(unittest.TestCase):
    def test_numeric_filename(self):
        result = audio_segment_sort("audio123.mp3")
        self.assertEqual(result, 123)

    def test_non_numeric_filename(self):
        result = audio_segment_sort("audio.mp3")
        self.assertEqual(result, float("inf"))


class TestSimplifyAudioName(unittest.TestCase):
    """
    segment_ctaudio_ridp0aa0br193031_cs80640000_mpd.m4s
    prefix: segment_ctaudio_rid
    manifest_id: p0aa0br193031
    segment_time: 80640000
    """

    def test_no_cinit_in_audio_name(self):
        manifest_id = "p0aa0br193031"
        audio_name = "segment_ctaudio_ridp0aa0br193031_cs80640000_mpd.m4s"
        expected_output = "80640000.m4s"
        self.assertEqual(simplify_audio_name(manifest_id, audio_name), expected_output)

    def test_cinit_in_audio_name(self):
        """segment_ctaudio_ridp0aa0br193031_cinit_mpd.m4s"""
        manifest_id = "p0aa0br193031"
        audio_name = "segment_ctaudio_ridp0aa0br193031_cinit_mpd.m4s"
        expected_output = "cinit.m4s"
        self.assertEqual(simplify_audio_name(manifest_id, audio_name), expected_output)


class TestCreateDirIfDoesNotExist(unittest.TestCase):
    def test_create_dir_when_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir) / "non_existent_dir"
            create_dir_if_does_not_exist(dir_path)
            self.assertTrue(os.path.exists(dir_path))

    def test_no_error_when_dir_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir) / "existing_dir"
            os.makedirs(dir_path)
            create_dir_if_does_not_exist(dir_path)
            self.assertTrue(os.path.exists(dir_path))

    def test_error_when_path_is_invalid(self):
        with self.assertRaises(OSError):
            create_dir_if_does_not_exist(Path("/invalid/path/with/invalid:characters"))


class TestDayMonthYear(unittest.TestCase):
    def test_valid_date_string(self):
        json_time = "2022-07-25T14:30:00+0200"
        expected_output = "25-07-2022"
        self.assertEqual(day_month_year(json_time), expected_output)

    def test_invalid_date_string_format(self):
        json_time = "2022-07-25 14:30:00+0200"  # missing 'T' separator
        with self.assertRaises(ValueError):
            day_month_year(json_time)


class TestTitleWithPart(unittest.TestCase):
    def test_part_as_integer(self):
        title = "Example Title"
        part = 1
        expected = "1-Example Title"
        self.assertEqual(title_with_part(title, part), expected)

    def test_part_as_string(self):
        title = "Example Title"
        part = "one"

        with self.assertRaises(ValueError):
            title_with_part(title, part)

    def test_no_part(self):
        title = "Example Title"
        expected = "Example Title"
        self.assertEqual(title_with_part(title), expected)

    def test_empty_title(self):
        title = ""
        part = 1
        with self.assertRaises(ValueError):
            title_with_part(title, part)

    def test_title_with_special_chars(self):
        title = "Example Title with @#$%"
        part = 1
        expected = "1-Example Title with @#$%"
        self.assertEqual(title_with_part(title, part), expected)


if __name__ == "__main__":
    unittest.main()
