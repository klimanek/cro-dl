import os
import shutil
from pathlib import Path

import unittest
from unittest.mock import MagicMock, patch

import tempfile
import asyncio
import aiohttp

from crodl.streams.download import download_part, download_parts, DownloadError


class TestDownloadPart(unittest.IsolatedAsyncioTestCase):
    async def test_successful_download(self):
        url = "https://example.com/file.txt"

        with tempfile.TemporaryDirectory() as target_folder:
            if not isinstance(target_folder, Path):
                target_folder = Path(target_folder)

            async with aiohttp.ClientSession() as session:
                with patch("aiohttp.ClientSession.get") as mock_get:
                    mock_response = MagicMock()
                    mock_response.status = 200
                    mock_response.content.read = MagicMock(
                        return_value=asyncio.Future()
                    )
                    mock_response.content.read.return_value.set_result(b"file content")
                    mock_get.return_value.__aenter__.return_value = mock_response

                    await download_part(url, session, target_folder)

                    self.assertTrue(os.path.exists(target_folder / "file.txt"))

    async def test_failed_download(self):
        url = "https://example.com/file.txt"
        target_folder = Path("/tmp")
        session = aiohttp.ClientSession()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = MagicMock(status=404)
            mock_get.return_value.__aenter__.return_value = mock_response

            with self.assertRaises(DownloadError):
                await download_part(url, session, target_folder)
            await session.close()

    async def test_invalid_url(self):
        url = "invalid_url"
        target_folder = Path("/tmp")
        session = aiohttp.ClientSession()

        try:
            with self.assertRaises(aiohttp.ClientError):
                await download_part(url, session, target_folder)
        finally:
            await session.close()

    async def test_non_existent_target_folder(self):
        url = "https://example.com/file.txt"
        # Create a temporary directory and then delete it to simulate a non-existent folder
        target_folder = Path(tempfile.mkdtemp())
        shutil.rmtree(target_folder)  # Remove the directory to simulate it not existing

        async with aiohttp.ClientSession() as session:
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.content.read = MagicMock(return_value=asyncio.Future())
                mock_response.content.read.return_value.set_result(b"file content")
                mock_get.return_value.__aenter__.return_value = mock_response

                # Attempt to download the file to a non-existent folder and catch the exception
                with self.assertRaises(FileNotFoundError):
                    await download_part(url, session, target_folder)


class TestDownloadParts(unittest.IsolatedAsyncioTestCase):
    async def test_download_multiple_parts(self):
        urls = [
            "https://example.com/file1.txt",
            "https://example.com/file2.txt",
            "https://example.com/file3.txt",
        ]

        with tempfile.TemporaryDirectory() as target_folder:
            if not isinstance(target_folder, Path):
                target_folder = Path(target_folder)

            print(f"Temporary directory created at: {target_folder}")

            async with aiohttp.ClientSession() as _:
                with patch("aiohttp.ClientSession.get") as mock_get:
                    # Create mock responses
                    mock_responses = []
                    for i in range(3):
                        mock_response = MagicMock()
                        mock_response.status = 200
                        mock_response.content.read = MagicMock(
                            return_value=asyncio.Future()
                        )
                        mock_response.content.read.return_value.set_result(
                            f"content of file {i + 1}".encode()
                        )

                        mock_response.__aenter__.return_value = mock_response
                        mock_response.__aexit__.return_value = None
                        mock_responses.append(mock_response)

                    mock_get.side_effect = mock_responses
                    await download_parts(urls, target_folder)

                    for i, url in enumerate(urls):
                        file_name = target_folder / os.path.basename(url)
                        self.assertTrue(
                            os.path.exists(file_name), f"{file_name} does not exist"
                        )


if __name__ == "__main__":
    unittest.main()
