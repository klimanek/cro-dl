import unittest
from unittest import mock

from crodl.settings import DOWNLOAD_PATH
from crodl.program.audiowork import AudioWork


class TestAudioWorkInit(unittest.TestCase):
    def setUp(self):
        self.mock_client = mock.Mock()
        self.mock_client.get_audio_uuid.return_value = "12345"
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Example Title",
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }

    def test_both_url_and_uuid_provided(self):
        with self.assertRaises(ValueError):
            AudioWork(url="https://example.com", uuid="12345", client=self.mock_client)

    def test_neither_url_nor_uuid_provided(self):
        with self.assertRaises(ValueError):
            AudioWork(client=self.mock_client)

    def test_only_url_provided(self):
        audio_work = AudioWork(url="https://example.com", client=self.mock_client)
        self.assertEqual(audio_work.url, "https://example.com")
        self.assertEqual(audio_work.uuid, "12345")
        self.assertEqual(audio_work.title, "Example Title")
        self.mock_client.get_audio_uuid.assert_called_once_with("https://example.com")
        self.mock_client.get_episode_data.assert_called_once_with("12345")

    def test_only_uuid_provided(self):
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertEqual(audio_work.uuid, "12345")
        self.assertEqual(audio_work.title, "Example Title")
        self.mock_client.get_audio_uuid.assert_not_called()
        self.mock_client.get_episode_data.assert_called_once_with("12345")

    def test_title_not_provided(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Test Title",
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(url="https://example.com", client=self.mock_client)
        self.assertEqual(audio_work.title, "Test Title")
        self.assertEqual(audio_work.audiowork_dir, DOWNLOAD_PATH / "Test Title")

    def test_title_provided(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(
            url="https://example.com", title="Test Title", client=self.mock_client
        )
        self.assertEqual(audio_work.title, "Test Title")

    def test_audiowork_dir_not_provided(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Test title",
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(url="https://example.com", client=self.mock_client)
        self.assertEqual(audio_work.audiowork_dir, DOWNLOAD_PATH / "Test title")

    def test_audiowork_dir_provided(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Test title",
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(
            url="https://example.com",
            audiowork_dir=DOWNLOAD_PATH / "TestTitle",
            client=self.mock_client,
        )
        self.assertEqual(audio_work.audiowork_dir, DOWNLOAD_PATH / "TestTitle")

    def test_series_and_show_not_provided(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(url="https://example.com", client=self.mock_client)
        self.assertFalse(audio_work.series)
        self.assertFalse(audio_work.show)
        self.mock_client.get_audio_uuid.assert_called_once_with(audio_work.url)
        self.mock_client.get_episode_data.assert_called_once_with("12345")


class TestAudioWorkLinks(unittest.TestCase):
    def setUp(self):
        self.mock_client = mock.Mock()
        self.mock_client.get_audio_uuid.return_value = "12345"

    def test_audio_links_present(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": [{"link": "test_link"}],
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertEqual(audio_work.audio_links, [{"link": "test_link"}])

    def test_audio_links_not_present(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": [],
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)

        self.assertIsNone(audio_work.audio_formats)


class TestAudioVariants(unittest.TestCase):
    def setUp(self):
        self.mock_client = mock.Mock()
        self.mock_client.get_audio_uuid.return_value = "12345"

    def test_audio_links_is_none(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": None,
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertIsNone(audio_work.audio_formats)

    def test_audio_links_is_empty_list(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": [],
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertIsNone(audio_work.audio_formats)

    def test_audio_links_has_no_variant_key(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": [{"key": "value"}],
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertIsNone(audio_work.audio_formats)

    def test_audio_links_has_variant_key(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": [{"variant": "mp3"}, {"variant": "aac"}],
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertEqual(audio_work.audio_formats, ["mp3", "aac"])

    def test_audio_links_is_not_a_list(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": "not a list",
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertIsNone(audio_work.audio_formats)


class TestAudioWorkFormats(unittest.TestCase):
    def setUp(self):
        self.mock_client = mock.Mock()
        self.mock_client.get_audio_uuid.return_value = "12345"

    def test_audio_formats_with_audio_links(self):
        expected_audio_links = [
            {"variant": "aac", "url": "https://example.com/aac.mp4"},
            {"variant": "m4a", "url": "https://example.com/m4a.mp4"},
        ]
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": expected_audio_links,
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        expected_result = {
            "aac": "https://example.com/aac.mp4",
            "m4a": "https://example.com/m4a.mp4",
        }
        self.assertEqual(audio_work.audio_formats_urls, expected_result)

    def test_audio_links_without_audio_links(self):
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "audioLinks": [],
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }

        audio_work = AudioWork(uuid="12345", client=self.mock_client)
        self.assertIsNone(audio_work.audio_formats)


if __name__ == "__main__":
    unittest.main()
