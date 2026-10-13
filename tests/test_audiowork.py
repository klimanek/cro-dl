import asyncio
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from crodl.settings import DOWNLOAD_PATH
from crodl.program.audiowork import AudioWork
from crodl.program.content import Collection
from crodl.streams.mp3 import MP3


def load(work):
    """Runs the async load() from a synchronous test and returns the work."""
    asyncio.run(work.load())
    return work


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

    def test_construction_does_no_io(self):
        # Regression (REFACTORING_TODO item 5): the constructor must stay pure.
        audio_work = AudioWork(url="https://example.com", client=self.mock_client)

        self.assertEqual(audio_work.uuid, None)
        self.assertEqual(audio_work.title, "Unknown")
        self.assertFalse(audio_work.loaded)
        self.mock_client.get_audio_uuid.assert_not_called()
        self.mock_client.get_episode_data.assert_not_called()

    def test_only_url_provided(self):
        audio_work = load(AudioWork(url="https://example.com", client=self.mock_client))
        self.assertEqual(audio_work.url, "https://example.com")
        self.assertEqual(audio_work.uuid, "12345")
        self.assertEqual(audio_work.title, "Example Title")
        self.assertTrue(audio_work.loaded)
        self.mock_client.get_audio_uuid.assert_called_once_with("https://example.com")
        self.mock_client.get_episode_data.assert_called_once_with("12345")

    def test_only_uuid_provided(self):
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
        self.assertEqual(audio_work.uuid, "12345")
        self.assertEqual(audio_work.title, "Example Title")
        self.mock_client.get_audio_uuid.assert_not_called()
        self.mock_client.get_episode_data.assert_called_once_with("12345")

    def test_load_is_idempotent(self):
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
        asyncio.run(audio_work.load())

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
        audio_work = load(AudioWork(url="https://example.com", client=self.mock_client))
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
        audio_work = load(
            AudioWork(
                url="https://example.com", title="Test Title", client=self.mock_client
            )
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
        audio_work = load(AudioWork(url="https://example.com", client=self.mock_client))
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
        audio_work = load(
            AudioWork(
                url="https://example.com",
                audiowork_dir=DOWNLOAD_PATH / "TestTitle",
                client=self.mock_client,
            )
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
        audio_work = load(AudioWork(url="https://example.com", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))

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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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
        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
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

        audio_work = load(AudioWork(uuid="12345", client=self.mock_client))
        self.assertIsNone(audio_work.audio_formats)


class TestAudioWorkAlreadyExists(unittest.TestCase):
    """already_exists() only inspects the disk, so no loading is required."""

    def _make_audio_work(self, audiowork_dir, title, remove_accents=False):
        mock_client = mock.Mock()
        mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": title,
                    "since": "2024-08-14T18:05:00+02:00",
                }
            }
        }
        return AudioWork(
            uuid="12345",
            title=title,
            audiowork_dir=audiowork_dir,
            remove_accents=remove_accents,
            client=mock_client,
        )

    def test_existing_file_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_work = self._make_audio_work(Path(tmp), "3 - Díl")
            (Path(tmp) / "3 - Díl.mp3").write_text("x", encoding="utf-8")
            self.assertTrue(audio_work.already_exists())

    def test_substring_does_not_match_other_part(self):
        # Regression: "3 - Díl" used to match "13 - Díl.mp3" via substring.
        with tempfile.TemporaryDirectory() as tmp:
            audio_work = self._make_audio_work(Path(tmp), "3 - Díl")
            (Path(tmp) / "13 - Díl.mp3").write_text("x", encoding="utf-8")
            self.assertFalse(audio_work.already_exists())

    def test_any_audio_extension_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_work = self._make_audio_work(Path(tmp), "Some Title")
            (Path(tmp) / "Some Title.aac").write_text("x", encoding="utf-8")
            self.assertTrue(audio_work.already_exists())

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_work = self._make_audio_work(Path(tmp), "Some Title")
            self.assertFalse(audio_work.already_exists())

    def test_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_work = self._make_audio_work(Path(tmp) / "does-not-exist", "Title")
            self.assertFalse(audio_work.already_exists())

    def test_no_accents_matches_the_stripped_file_name(self):
        # Regression: with --no-accents the file kept its diacritics, so
        # already_exists() never found it.
        with tempfile.TemporaryDirectory() as tmp:
            audio_work = self._make_audio_work(
                Path(tmp), "Příliš žluťoučký", remove_accents=True
            )
            (Path(tmp) / "Prilis zlutoucky.mp3").write_text("x", encoding="utf-8")
            self.assertTrue(audio_work.already_exists())


class TestRemoveAccentsPropagation(unittest.IsolatedAsyncioTestCase):
    """AudioWork must hand `remove_accents` down to every downloader."""

    async def _make_audio_work(self, audio_links):
        client = mock.Mock()
        client.session = mock.Mock()
        client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Title",
                    "since": "2024-08-14T18:05:00+02:00",
                    "audioLinks": audio_links,
                }
            }
        }
        audio_work = AudioWork(
            uuid="12345",
            title="Title",
            audiowork_dir=Path("/tmp/unused"),
            remove_accents=True,
            client=client,
        )
        await audio_work.load()
        return audio_work

    async def test_mp3_receives_remove_accents(self):
        audio_work = await self._make_audio_work([{"variant": "mp3", "url": "u.mp3"}])
        with mock.patch("crodl.program.audiowork.MP3") as mock_mp3:
            mock_mp3.return_value.download = mock.AsyncMock()
            await audio_work._download_mp3()

        self.assertTrue(mock_mp3.call_args.kwargs["remove_accents"])

    async def test_hls_receives_remove_accents(self):
        audio_work = await self._make_audio_work([{"variant": "hls", "url": "u.m3u8"}])
        with mock.patch("crodl.program.audiowork.HLS") as mock_hls:
            mock_hls.return_value.download = mock.AsyncMock()
            await audio_work._download_hls()

        self.assertTrue(mock_hls.call_args.kwargs["remove_accents"])

    async def test_dash_receives_remove_accents(self):
        audio_work = await self._make_audio_work([{"variant": "dash", "url": "u.mpd"}])
        with mock.patch("crodl.program.audiowork.DASH") as mock_dash:
            mock_dash.return_value.download = mock.AsyncMock()
            await audio_work._download_dash()

        self.assertTrue(mock_dash.call_args.kwargs["remove_accents"])


class TestAudioWorkInfoAndNoIO(unittest.TestCase):
    """The core must return data, not print (REFACTORING_TODO item 4)."""

    def _make_audio_work(self, attributes):
        client = mock.Mock()
        client.get_episode_data.return_value = {"data": {"attributes": attributes}}
        return load(AudioWork(uuid="12345", title="Title", client=client))

    def test_info_returns_variant_rows(self):
        audio_work = self._make_audio_work(
            {
                "since": "2024-08-14T18:05:00+02:00",
                "audioLinks": [
                    {
                        "variant": "mp3",
                        "bitrate": 128,
                        "duration": 3600,
                        "sizeInBytes": 1024,
                    },
                    {"variant": "hls", "bitrate": 128, "duration": 3600},
                ],
            }
        )

        self.assertEqual(
            audio_work.info(),
            [
                {
                    "variant": "mp3",
                    "bitrate": 128,
                    "duration_seconds": 3600,
                    "size_bytes": 1024,
                },
                {
                    "variant": "hls",
                    "bitrate": 128,
                    "duration_seconds": 3600,
                    "size_bytes": None,
                },
            ],
        )

    def test_info_is_empty_without_links(self):
        audio_work = self._make_audio_work({"since": "2024-08-14T18:05:00+02:00"})
        self.assertEqual(audio_work.info(), [])

    def test_missing_links_write_nothing_to_stdout(self):
        audio_work = self._make_audio_work({"since": "2024-08-14T18:05:00+02:00"})
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            self.assertIsNone(audio_work.audio_links)
            self.assertIsNone(audio_work.audio_formats)
            self.assertEqual(audio_work.info(), [])

        self.assertEqual(buffer.getvalue(), "")

    def test_unavailable_reason_for_aired_episode(self):
        audio_work = self._make_audio_work({"since": "2024-08-14T18:05:00+02:00"})
        self.assertIn("14.08.2024", audio_work.unavailable_reason)

    def test_unavailable_reason_for_future_episode(self):
        audio_work = self._make_audio_work({"since": "2999-01-01T10:00:00+01:00"})
        self.assertIn("bude uvedena", audio_work.unavailable_reason)


class TestDownloadedHook(unittest.IsolatedAsyncioTestCase):
    """The facade stores finished downloads through this core hook."""

    async def test_download_reports_the_finished_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = mock.Mock()
            client.session = mock.Mock()
            client.get_episode_data.return_value = {
                "data": {
                    "attributes": {
                        "title": "3 - Díl",
                        "since": "2024-08-14T18:05:00+02:00",
                        "audioLinks": [{"variant": "mp3", "url": "u.mp3"}],
                    }
                }
            }
            audio_work = AudioWork(
                uuid="12345", title="3 - Díl", audiowork_dir=Path(tmp), client=client
            )
            recorded = []

            async def hook(work, path, collection=None):
                recorded.append((work, path, collection))

            with mock.patch.object(MP3, "download", new=mock.AsyncMock()):
                await audio_work.download(on_downloaded=hook)

            self.assertEqual(recorded, [(audio_work, Path(tmp) / "3 - Díl.mp3", None)])

    async def test_download_hands_the_collection_to_the_hook(self):
        """A part of a series must tell the library which series it belongs to."""
        with tempfile.TemporaryDirectory() as tmp:
            client = mock.Mock()
            client.session = mock.Mock()
            client.get_episode_data.return_value = {
                "data": {
                    "attributes": {
                        "title": "3 - Díl",
                        "since": "2024-08-14T18:05:00+02:00",
                        "audioLinks": [{"variant": "mp3", "url": "u.mp3"}],
                    }
                }
            }
            audio_work = AudioWork(
                uuid="12345", title="3 - Díl", audiowork_dir=Path(tmp), client=client
            )
            collection = Collection(
                uuid="series-1",
                type="series",
                title="Seriál",
                shared_asset_url="https://example.com/cover.jpg",
            )
            recorded = []

            async def hook(work, path, received=None):
                recorded.append(received)

            with mock.patch.object(MP3, "download", new=mock.AsyncMock()):
                await audio_work.download(on_downloaded=hook, collection=collection)

            self.assertEqual(recorded, [collection])

    async def test_download_without_a_hook_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = mock.Mock()
            client.session = mock.Mock()
            client.get_episode_data.return_value = {
                "data": {
                    "attributes": {
                        "title": "Díl",
                        "since": "2024-08-14T18:05:00+02:00",
                        "audioLinks": [{"variant": "mp3", "url": "u.mp3"}],
                    }
                }
            }
            audio_work = AudioWork(
                uuid="12345", title="Díl", audiowork_dir=Path(tmp), client=client
            )

            with mock.patch.object(MP3, "download", new=mock.AsyncMock()):
                await audio_work.download()

            self.assertTrue(audio_work.loaded)


class TestAudioWorkMetadataProperties(unittest.TestCase):
    """Fields the library stores must be readable from the core."""

    def _make(self, attributes):
        client = mock.Mock()
        client.get_episode_data.return_value = {"data": {"attributes": attributes}}
        return load(AudioWork(uuid="12345", title="Title", client=client))

    def test_short_title_part_and_duration(self):
        audio_work = self._make(
            {
                "since": "2024-08-14T18:05:00+02:00",
                "shortTitle": "Krátce",
                "part": 3,
                "audioLinks": [{"variant": "mp3", "url": "u.mp3", "duration": 3229}],
            }
        )

        self.assertEqual(audio_work.short_title, "Krátce")
        self.assertEqual(audio_work.part, 3)
        self.assertEqual(audio_work.duration, 3229)

    def test_metadata_properties_are_none_without_api_data(self):
        audio_work = self._make({"since": "2024-08-14T18:05:00+02:00"})

        self.assertIsNone(audio_work.short_title)
        self.assertIsNone(audio_work.part)
        self.assertIsNone(audio_work.duration)

    def test_non_numeric_part_is_ignored(self):
        audio_work = self._make({"since": "2024-08-14T18:05:00+02:00", "part": "extra"})

        self.assertIsNone(audio_work.part)


class TestAudioWorkAssetUrl(unittest.TestCase):
    """The episode's artwork URL, as the log from the real library showed it."""

    def _make(self, attributes):
        client = mock.Mock()
        client.get_episode_data.return_value = {"data": {"attributes": attributes}}
        return load(AudioWork(uuid="12345", title="Title", client=client))

    def test_nested_asset_object_yields_its_url(self):
        # Regression: str() of the asset dict used to be handed to the
        # downloader, which failed with an "InvalidURL" on every episode.
        audio_work = self._make(
            {
                "since": "2024-08-14T18:05:00+02:00",
                "asset": {
                    "id": "4a588db5-ced8-3baa-87e3-041acdc45483",
                    "url": "https://portal.rozhlas.cz/images/02fd4cae.jpg",
                    "width": 3620,
                    "height": 2277,
                    "focal_point": "55,92",
                    "credit": {"source": "Prodimedia"},
                    "inherited": True,
                },
            }
        )

        self.assertEqual(
            audio_work.asset_url, "https://portal.rozhlas.cz/images/02fd4cae.jpg"
        )

    def test_asset_url_is_none_without_api_data(self):
        audio_work = self._make({"since": "2024-08-14T18:05:00+02:00"})

        self.assertIsNone(audio_work.asset_url)


if __name__ == "__main__":
    unittest.main()
