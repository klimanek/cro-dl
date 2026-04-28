import os
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import tempfile
from pathlib import Path

from crodl.streams.mp3 import MP3


class TestMP3Download(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mp3 = MP3(
            url="http://example.com/audio.mp3",
            audiowork_dir=Path(self.temp_dir.name),
            audio_title="My Audio",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    async def test_download_success(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Length": "1024"}

        async def mock_iter_chunked(*args, **kwargs):
            yield b"fake audio data"

        mock_response.content.iter_chunked = MagicMock(side_effect=mock_iter_chunked)

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_response
            await self.mp3.download()

        # Check if the file was created in the temporary directory
        expected_file_path = os.path.join(self.temp_dir.name, "My Audio.mp3")  # type: ignore
        self.assertTrue(os.path.exists(expected_file_path))

    async def test_download_no_content_length(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}

        async def mock_iter_chunked(*args, **kwargs):
            yield b"fake audio data"

        mock_response.content.iter_chunked = MagicMock(side_effect=mock_iter_chunked)

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_response
            # Should not raise ValueError anymore
            await self.mp3.download()

        expected_file_path = os.path.join(self.temp_dir.name, "My Audio.mp3")  # type: ignore
        self.assertTrue(os.path.exists(expected_file_path))


if __name__ == "__main__":
    unittest.main()
