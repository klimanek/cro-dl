import unittest
from pathlib import Path
from unittest import mock

from crodl.data.attributes import Episodes
from crodl.program.series import Series
from crodl.program.show import Show

# Both collections receive the same API episode shape.
EPISODES = [
    {
        "id": "e1",
        "attributes": {
            "title": "První díl",
            "part": 1,
            "since": "2024-01-01T10:00:00+01:00",
            "audioLinks": [{"variant": "mp3", "url": "https://example.com/1.mp3"}],
        },
    },
    {
        "id": "e2",
        "attributes": {
            "title": "Druhý díl",
            "part": 2,
            "since": "2024-01-02T10:00:00+01:00",
            "audioLinks": [{"variant": "hls", "url": "https://example.com/2.m3u8"}],
        },
    },
]

EXPECTED_INFO = [
    {
        "uuid": "e1",
        "title": "1-První díl",
        "url": "https://example.com/1.mp3",
        "since": "2024-01-01T10:00:00+01:00",
        "part": 1,
    },
    {
        "uuid": "e2",
        "title": "2-Druhý díl",
        "url": "https://example.com/2.m3u8",
        "since": "2024-01-02T10:00:00+01:00",
        "part": 2,
    },
]


class TestEpisodesMapping(unittest.TestCase):
    def test_info_maps_episodes_and_prefixes_the_part(self):
        episodes = Episodes(title="Seriál", uuid="u", data=EPISODES, count=2)
        self.assertEqual(episodes.info, EXPECTED_INFO)

    def test_info_is_empty_for_an_empty_collection(self):
        self.assertEqual(Episodes().info, [])

    def test_missing_title_falls_back_to_unknown(self):
        episodes = Episodes(data=[{"id": "e1", "attributes": {"part": 1}}])
        self.assertEqual(episodes.info[0]["title"], "1-Unknown")

    def test_missing_part_keeps_the_plain_title(self):
        episodes = Episodes(data=[{"id": "e1", "attributes": {"title": "Sólo"}}])
        self.assertEqual(episodes.info[0]["title"], "Sólo")

    def test_repr_uses_the_collection_title(self):
        self.assertEqual(str(Episodes(title="Seriál")), "<Episodes of Seriál>")


class TestSeriesAndShowShareOneMechanism(unittest.IsolatedAsyncioTestCase):
    """Series and Show must build their episode lists the same way."""

    def _client(self):
        client = mock.Mock()
        client.get_related_data.return_value = {
            "data": EPISODES,
            "meta": {"count": len(EPISODES)},
        }
        client.get_series_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Seriál",
                    "totalParts": len(EPISODES),
                    "playable": True,
                }
            }
        }
        client.get_show_data.return_value = {
            "data": {
                "type": "show",
                "id": "sh",
                "attributes": {
                    "title": "Pořad",
                    "active": True,
                    "aired": True,
                    "description": "Popis",
                    "shortDescription": "Krátce",
                },
            }
        }
        return client

    async def test_series_and_show_yield_the_same_episode_info(self):
        client = self._client()

        series = Series(uuid="s", client=client, download_dir=Path("/tmp/unused"))
        show = Show(uuid="sh", client=client, download_dir=Path("/tmp/unused"))
        await series.load()
        await show.load()

        self.assertEqual(series.list_all_series_episodes(), EXPECTED_INFO)
        self.assertEqual(series.list_all_series_episodes(), show.episodes.info)

    async def test_series_reuses_the_cached_episodes(self):
        client = self._client()
        series = Series(uuid="s", client=client, download_dir=Path("/tmp/unused"))
        await series.load()

        self.assertIs(series.episodes.data, series.episodes_data)
        # the raw payload sits in exactly one place
        self.assertIs(series.episodes.data, EPISODES)


if __name__ == "__main__":
    unittest.main()
