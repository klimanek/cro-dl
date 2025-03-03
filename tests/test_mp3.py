import os
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO
import tempfile
from pathlib import Path

from crodl.streams.mp3 import MP3


class TestMP3Download(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mp3 = MP3(
            url="http://example.com/audio.mp3",
            audiowork_dir=Path(self.temp_dir.name),
            audio_title="My Audio",
        )

    @patch("requests.get")
    def test_download_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "1024"}
        mock_response.raw = BytesIO(b"fake audio data")
        mock_get.return_value.__enter__.return_value = mock_response

        self.mp3.download()

        # Check if the file was created in the temporary directory
        expected_file_path = os.path.join(self.temp_dir.name, "My Audio.mp3")  # type: ignore
        self.assertTrue(os.path.exists(expected_file_path))

    @patch("requests.get")
    def test_download_no_content_length(self, mock_get):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.temp_dir = temp_dir
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_get.return_value.__enter__.return_value = mock_response

            with self.assertRaises(ValueError):
                self.mp3.download()


if __name__ == "__main__":
    unittest.main()
