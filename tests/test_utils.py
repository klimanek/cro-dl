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
    sanitize_filename,
    slugify,
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


class TestSanitizeFilename(unittest.TestCase):
    def test_remove_invalid_chars(self):
        title = 'Title with < > : " / \\ | ? *'
        expected = "Title with -"  # Colon and slashes are replaced by - and space, others removed
        # After my implementation:
        # : -> " -"
        # / -> "-"
        # \ -> "-"
        # <>|"*? -> removed
        sanitized = sanitize_filename(title)
        self.assertEqual(sanitized, expected)
        self.assertNotIn("<", sanitized)

        self.assertNotIn(">", sanitized)
        self.assertNotIn("?", sanitized)
        self.assertNotIn("*", sanitized)

    def test_remove_accents(self):
        title = "Příliš žluťoučký kůň úpěl ďábelské ódy"
        expected = "Prilis zlutoucky kun upel dabelske ody"
        self.assertEqual(sanitize_filename(title, remove_accents=True), expected)

    def test_trailing_dots_and_spaces(self):
        title = "Title with trailing dot. "
        expected = "Title with trailing dot"
        self.assertEqual(sanitize_filename(title), expected)


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

    def test_with_accent_removal(self):
        title = "Hra s češtinou"
        processed = process_audiowork_title(title, remove_accents=True)
        self.assertEqual(processed, "Hra s cestinou")


class TestSlugify(unittest.TestCase):
    def test_basic_slug(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")

    def test_czech_slug(self):
        self.assertEqual(slugify("Příliš žluťoučký kůň"), "prilis-zlutoucky-kun")


class TestAudioSegmentSort(unittest.TestCase):
    def test_numeric_filename(self):
        result = audio_segment_sort("audio123.mp3")
        self.assertEqual(result, 123)

    def test_non_numeric_filename(self):
        result = audio_segment_sort("audio.mp3")
        self.assertEqual(result, float("inf"))


class TestSimplifyAudioName(unittest.TestCase):
    def test_no_cinit_in_audio_name(self):
        manifest_id = "p0aa0br193031"
        audio_name = "segment_ctaudio_ridp0aa0br193031_cs80640000_mpd.m4s"
        expected_output = "80640000.m4s"
        self.assertEqual(simplify_audio_name(manifest_id, audio_name), expected_output)

    def test_cinit_in_audio_name(self):
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


class TestDayMonthYear(unittest.TestCase):
    def test_valid_date_string(self):
        json_time = "2022-07-25T14:30:00+0200"
        expected_output = "25-07-2022"
        self.assertEqual(day_month_year(json_time), expected_output)


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


if __name__ == "__main__":
    unittest.main()
