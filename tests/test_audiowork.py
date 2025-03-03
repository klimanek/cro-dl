import unittest
from unittest import mock
from unittest.mock import patch

from crodl.settings import DOWNLOAD_PATH
from crodl.program.audiowork import AudioWork


class TestAudioWorkInit(unittest.TestCase):
    def test_both_url_and_uuid_provided(self):
        with self.assertRaises(ValueError):
            AudioWork(url="https://example.com", uuid="12345")

    def test_neither_url_nor_uuid_provided(self):
        with self.assertRaises(ValueError):
            AudioWork()

    @patch("crodl.program.audiowork.get_audio_uuid")
    @patch("crodl.program.audiowork.get_attributes")
    def test_only_url_provided(self, mock_get_attributes, mock_get_audio_uuid):
        mock_get_audio_uuid.return_value = "12345"
        mock_get_attributes.return_value = {
            "title": "Example Title",
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(url="https://example.com")
        self.assertEqual(audio_work.url, "https://example.com")
        self.assertEqual(audio_work.uuid, "12345")
        self.assertEqual(audio_work.title, "Example Title")

    @patch("crodl.program.audiowork.get_attributes")
    def test_only_uuid_provided(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "title": "Example Title",
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertEqual(audio_work.uuid, "12345")
        self.assertEqual(audio_work.title, "Example Title")

    @patch("crodl.program.audiowork.get_audio_uuid")
    @patch("crodl.program.audiowork.get_attributes")
    def test_title_not_provided(self, mock_get_attributes, mock_get_audio_uuid):
        mock_get_audio_uuid.return_value = "12345"
        mock_get_attributes.return_value = {
            "title": "Test Title",
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(url="https://example.com")
        self.assertEqual(audio_work.title, "Test Title")
        self.assertEqual(audio_work.audiowork_dir, DOWNLOAD_PATH / "Test Title")

    @patch("crodl.program.audiowork.get_audio_uuid")
    @patch("crodl.program.audiowork.get_attributes")
    def test_title_provided(self, mock_get_attributes, mock_get_audio_uuid):
        mock_get_audio_uuid.return_value = "12345"
        mock_get_attributes.return_value = {
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(url="https://example.com", title="Test Title")
        self.assertEqual(audio_work.title, "Test Title")

    @patch("crodl.program.audiowork.get_audio_uuid")
    @patch("crodl.program.audiowork.get_attributes")
    def test_audiowork_dir_not_provided(self, mock_get_attributes, mock_get_audio_uuid):
        mock_get_audio_uuid.return_value = "12345"
        mock_get_attributes.return_value = {
            "title": "Test title",
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(url="https://example.com")
        self.assertEqual(audio_work.audiowork_dir, DOWNLOAD_PATH / "Test title")

    @patch("crodl.program.audiowork.get_audio_uuid")
    @patch("crodl.program.audiowork.get_attributes")
    def test_audiowork_dir_provided(self, mock_get_attributes, mock_get_audio_uuid):
        mock_get_audio_uuid.return_value = "12345"
        mock_get_attributes.return_value = {
            "title": "Test title",
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(
            url="https://example.com", audiowork_dir=DOWNLOAD_PATH / "TestTitle"
        )
        self.assertEqual(audio_work.audiowork_dir, DOWNLOAD_PATH / "TestTitle")

    @patch("crodl.program.audiowork.get_audio_uuid")
    @patch("crodl.program.audiowork.get_attributes")
    def test_series_and_show_not_provided(
        self, mock_get_attributes, mock_get_audio_uuid
    ):
        mock_get_audio_uuid.return_value = "12345"
        mock_get_attributes.return_value = {
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(url="https://example.com")
        self.assertFalse(audio_work.series)
        self.assertFalse(audio_work.show)
        mock_get_audio_uuid.assert_called_once_with(
            audio_work.url, mock.ANY
        )  # Use mock.ANY to match any argument
        mock_get_attributes.assert_called_once_with("12345", mock.ANY)


class TestAudioWorkLinks(unittest.TestCase):
    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_present(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": [{"link": "test_link"}],
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertEqual(audio_work.audio_links, [{"link": "test_link"}])

    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_not_present(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": [],
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")

        self.assertIsNone(audio_work.audio_formats)


class TestAudioVariants(unittest.TestCase):
    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_is_none(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": None,
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertIsNone(audio_work.audio_formats)

    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_is_empty_list(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": [],
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertIsNone(audio_work.audio_formats)

    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_has_no_variant_key(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": [{"key": "value"}],
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertIsNone(audio_work.audio_formats)

    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_has_variant_key(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": [{"variant": "mp3"}, {"variant": "aac"}],
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertEqual(audio_work.audio_formats, ["mp3", "aac"])

    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_is_not_a_list(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": "not a list",
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        self.assertIsNone(audio_work.audio_formats)


class TestAudioWorkFormats(unittest.TestCase):
    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_formats_with_audio_links(self, mock_get_attributes):
        expected_audio_links = [
            {"variant": "aac", "url": "https://example.com/aac.mp4"},
            {"variant": "m4a", "url": "https://example.com/m4a.mp4"},
        ]
        mock_get_attributes.return_value = {
            "audioLinks": expected_audio_links,
            "since": "2024-08-14T18:05:00+02:00",
        }
        audio_work = AudioWork(uuid="12345")
        expected_result = {
            "aac": "https://example.com/aac.mp4",
            "m4a": "https://example.com/m4a.mp4",
        }
        self.assertEqual(audio_work.audio_formats_urls, expected_result)

    @patch("crodl.program.audiowork.get_attributes")
    def test_audio_links_without_audio_links(self, mock_get_attributes):
        mock_get_attributes.return_value = {
            "audioLinks": [],
            "since": "2024-08-14T18:05:00+02:00",
        }

        audio_work = AudioWork(uuid="12345")
        self.assertIsNone(audio_work.audio_formats)


if __name__ == "__main__":
    unittest.main()
