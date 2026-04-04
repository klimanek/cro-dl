import os
import unittest
from unittest.mock import MagicMock
from io import BytesIO
import tempfile
from pathlib import Path

from crodl.streams.mp3 import MP3


class TestMP3Download(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_session = MagicMock()
        self.mp3 = MP3(
            url="http://example.com/audio.mp3",
            audiowork_dir=Path(self.temp_dir.name),
            audio_title="My Audio",
            session=self.mock_session,
        )

    def test_download_success(self):
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "1024"}
        mock_response.raw = BytesIO(b"fake audio data")
        self.mock_session.get.return_value.__enter__.return_value = mock_response

        self.mp3.download()

        # Check if the file was created in the temporary directory
        expected_file_path = os.path.join(self.temp_dir.name, "My Audio.mp3")  # type: ignore
        self.assertTrue(os.path.exists(expected_file_path))

    def test_download_no_content_length(self):
        mock_response = MagicMock()
        mock_response.headers = {}
        self.mock_session.get.return_value.__enter__.return_value = mock_response

        with self.assertRaises(ValueError):
            self.mp3.download()


if __name__ == "__main__":
    unittest.main()
