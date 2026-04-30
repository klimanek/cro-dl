import unittest
from unittest.mock import patch, MagicMock
import subprocess

from crodl.main import check_ffmpeg


class TestFFmpegCheck(unittest.TestCase):
    @patch("subprocess.run")
    def test_ffmpeg_present(self, mock_run):
        """Test situation when ffmpeg is installed."""
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(check_ffmpeg())
        mock_run.assert_called_with(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    @patch("subprocess.run")
    def test_ffmpeg_missing(self, mock_run):
        """Test situation when ffmpeg is not installed."""
        mock_run.side_effect = FileNotFoundError()
        self.assertFalse(check_ffmpeg())

    @patch("subprocess.run")
    def test_ffmpeg_error(self, mock_run):
        """Test situation when ffmpeg returns an error."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
        self.assertFalse(check_ffmpeg())


if __name__ == "__main__":
    unittest.main()
