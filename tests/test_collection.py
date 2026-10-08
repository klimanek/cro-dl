import asyncio
import unittest
from pathlib import Path
from unittest import mock

from crodl.data.attributes import extract_asset_url
from crodl.program.content import shared_artwork_url
from crodl.program.series import Series
from crodl.program.show import Show

SHARED_ASSET = "https://portal.rozhlas.cz/sites/default/files/images/02fd4cae62538bde4c336be956395c3e.jpg"
OTHER_ASSET = (
    "https://portal.rozhlas.cz/sites/default/files/images/cover-of-part-two.jpg"
)

# What the content API reports for an episode: the artwork is nested in `asset`.
INHERITED_ASSET = {
    "id": "4a588db5-ced8-3baa-87e3-041acdc45483",
    "url": SHARED_ASSET,
    "width": 3620,
    "height": 2277,
    "focal_point": "55,92",
    "credit": {"source": "Prodimedia", "description": "Bohumil Hrabal"},
    "inherited": True,
}


def episode(part: int, asset: object = None) -> dict:
    attributes: dict = {
        "title": f"Díl {part}",
        "part": part,
        "since": f"2024-01-0{part}T10:00:00+01:00",
        "audioLinks": [{"variant": "mp3", "url": f"https://example.com/{part}.mp3"}],
    }
    if asset is not None:
        attributes["asset"] = asset
    return {"id": f"e{part}", "attributes": attributes}


class TestExtractAssetUrl(unittest.TestCase):
    def test_takes_the_url_from_the_asset_object(self):
        self.assertEqual(extract_asset_url({"asset": INHERITED_ASSET}), SHARED_ASSET)

    def test_asset_object_without_a_url(self):
        self.assertIsNone(extract_asset_url({"asset": {"id": "a-1"}}))

    def test_plain_url_string_is_accepted(self):
        self.assertEqual(extract_asset_url({"asset": OTHER_ASSET}), OTHER_ASSET)

    def test_missing_asset_is_none(self):
        self.assertIsNone(extract_asset_url({}))
        self.assertIsNone(extract_asset_url({"asset": None}))
        self.assertIsNone(extract_asset_url({"asset": {}}))


class TestSharedArtworkUrl(unittest.TestCase):
    """One work's parts share an image; separate works bring their own."""

    def test_parts_with_the_same_image_share_it(self):
        parts = [episode(1, INHERITED_ASSET), episode(2, INHERITED_ASSET)]
        self.assertEqual(shared_artwork_url(parts), SHARED_ASSET)

    def test_parts_with_their_own_images_do_not_share(self):
        parts = [episode(1, SHARED_ASSET), episode(2, OTHER_ASSET)]
        self.assertIsNone(shared_artwork_url(parts))

    def test_a_single_part_has_no_shared_image(self):
        self.assertIsNone(shared_artwork_url([episode(1, SHARED_ASSET)]))

    def test_no_parts_and_no_images(self):
        self.assertIsNone(shared_artwork_url([]))
        self.assertIsNone(shared_artwork_url([episode(1), episode(2)]))

    def test_a_part_without_an_image_still_shares_the_other_one(self):
        parts = [episode(1, INHERITED_ASSET), episode(2)]
        self.assertEqual(shared_artwork_url(parts), SHARED_ASSET)


class CollectionTestCase(unittest.IsolatedAsyncioTestCase):
    """Builds loaded collections with a mocked API client (no network)."""

    assets: list[object] = [INHERITED_ASSET, INHERITED_ASSET]

    def _client(self) -> mock.Mock:
        client = mock.Mock()
        parts = [episode(index + 1, asset) for index, asset in enumerate(self.assets)]
        client.get_related_data.return_value = {
            "data": parts,
            "meta": {"count": len(parts)},
        }
        client.get_series_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Seriál",
                    "totalParts": len(parts),
                    "playable": True,
                    "description": "<p>Popis seriálu</p>",
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
                    "description": "Popis pořadu",
                    "shortDescription": "Krátce",
                    "asset": INHERITED_ASSET,
                },
            }
        }
        return client

    async def _load_series(self) -> Series:
        series = Series(
            uuid="s", client=self._client(), download_dir=Path("/tmp/unused")
        )
        await series.load()
        return series

    async def _load_show(self) -> Show:
        show = Show(uuid="sh", client=self._client(), download_dir=Path("/tmp/unused"))
        await show.load()
        return show


class TestSeriesCollection(CollectionTestCase):
    def test_collection_carries_the_series_itself(self):
        series = asyncio.run(self._load_series())
        collection = series.collection

        self.assertEqual(collection.uuid, "s")
        self.assertEqual(collection.type, "series")
        self.assertEqual(collection.title, "Seriál")
        self.assertEqual(collection.description, "Popis seriálu")
        self.assertEqual(collection.shared_asset_url, SHARED_ASSET)

    def test_series_asset_url_comes_from_the_asset_object(self):
        client = self._client()
        client.get_series_data.return_value["data"]["attributes"]["asset"] = (
            INHERITED_ASSET
        )
        series = Series(uuid="s", client=client, download_dir=Path("/tmp/unused"))
        asyncio.run(series.load())

        self.assertEqual(series.asset_url, SHARED_ASSET)


class TestShowCollection(CollectionTestCase):
    def test_collection_carries_the_show_itself(self):
        show = asyncio.run(self._load_show())
        collection = show.collection

        self.assertEqual(collection.uuid, "sh")
        self.assertEqual(collection.type, "show")
        self.assertEqual(collection.title, "Pořad")
        self.assertEqual(collection.description, "Popis pořadu")
        self.assertEqual(collection.shared_asset_url, SHARED_ASSET)

    def test_show_asset_url_comes_from_the_asset_object(self):
        show = asyncio.run(self._load_show())
        self.assertEqual(show.asset_url, SHARED_ASSET)


class TestCollectionWithoutASharedImage(CollectionTestCase):
    assets = [SHARED_ASSET, OTHER_ASSET]

    def test_parts_of_separate_works_keep_their_own_images(self):
        series = asyncio.run(self._load_series())
        self.assertIsNone(series.collection.shared_asset_url)


if __name__ == "__main__":
    unittest.main()
