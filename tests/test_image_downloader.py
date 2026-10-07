import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp

from crodl.tools.image_downloader import download_image


class TestDownloadImage(unittest.IsolatedAsyncioTestCase):
    async def test_success_saves_file_and_returns_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Nested path: the parent directory does not exist yet.
            target = Path(tmp) / "covers" / "episode.jpg"

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(return_value=b"fake-image-bytes")

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_response
                result = await download_image("http://example.com/img.jpg", target)

            self.assertEqual(result, target)
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), b"fake-image-bytes")

    async def test_non_200_returns_none_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "episode.jpg"

            mock_response = AsyncMock()
            mock_response.status = 404

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_response
                result = await download_image("http://example.com/missing.jpg", target)

            self.assertIsNone(result)
            self.assertFalse(target.exists())

    async def test_error_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "episode.jpg"

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.side_effect = aiohttp.ClientError("boom")
                result = await download_image("http://example.com/img.jpg", target)

            self.assertIsNone(result)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
