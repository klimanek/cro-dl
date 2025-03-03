# tests/test_audioparts.py
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from crodl.streams.audioparts import AudioParts
from crodl.streams.utils import create_dir_if_does_not_exist, process_audiowork_title


class TestAudioParts(unittest.TestCase):
    def setUp(self):
        self.title = "Some Title"
        self.url = "https://example.com"
        self.audio_parts = AudioParts(url=self.url, audio_title=self.title)

    def test_init(self):
        self.assertEqual(self.audio_parts.url, self.url)
        self.assertEqual(self.audio_parts.audio_title, self.title)

    def test_create_dir_if_does_not_exist_real_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir = Path(tmp_dir)
            dir_path = tmp_dir / "test_dir"
            create_dir_if_does_not_exist(dir_path)
            self.assertTrue(os.path.exists(dir_path))


class TestMergeChunks(unittest.TestCase):
    def setUp(self):
        self.audio_parts = AudioParts("url", "audio_title")

    @patch("subprocess.run")
    def test_supported_audio_format_m4a(self, mock_subprocess_run):
        self.audio_parts._merge_chunks("m4a")  # pylint: disable=protected-access
        mock_subprocess_run.assert_called_once()

    @patch("subprocess.run")
    def test_supported_audio_format_aac(self, mock_subprocess_run):
        self.audio_parts._merge_chunks("aac")  # pylint: disable=protected-access
        mock_subprocess_run.assert_called_once()

    def test_unsupported_audio_format(self):
        with self.assertRaises(ValueError):
            self.audio_parts._merge_chunks("mp3")  # pylint: disable=protected-access

    @patch("subprocess.run")
    def test_subprocess_run_args(self, mock_subprocess_run):
        self.audio_parts._merge_chunks("m4a")  # pylint: disable=protected-access

        expected_command = [
            "ffmpeg",
            "-i",
            "concatf:list.txt",
            "-c",
            "copy",
            f"../{process_audiowork_title(self.audio_parts.audio_title)}.m4a",
            "-loglevel",
            "quiet",
        ]
        mock_subprocess_run.assert_called_once_with(
            expected_command, cwd=str(self.audio_parts.segments_path), check=True
        )


if __name__ == "__main__":
    unittest.main()
