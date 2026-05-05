import os
import unittest
import tempfile
from pathlib import Path
from typing import Optional, Any
from rich.progress import Progress

from crodl.streams.audioparts import AudioParts


class DummyAudioParts(AudioParts):
    async def download(self, progress: Optional[Progress] = None, task_id: Optional[Any] = None) -> None:
        """Mock download implementation for testing."""
        pass


class TestAudioParts(unittest.TestCase):
    def setUp(self):
        self.url = "http://example.com/audio.mp3"
        self.audio_title = "Test Audio"
        self.audiowork_dir = Path("/path/to/audio")
        self.segments_path = Path("/path/to/segments")
        self.downloader = DummyAudioParts(
            url=self.url,
            audio_title=self.audio_title,
            audiowork_dir=self.audiowork_dir,
            segments_path=self.segments_path,
        )

    def test_post_init_sets_paths(self):
        self.assertEqual(self.downloader.url, self.url)
        self.assertEqual(self.downloader.audio_title, self.audio_title)
        self.assertEqual(self.downloader.audiowork_dir, self.audiowork_dir)
        self.assertEqual(self.downloader.segments_path, self.segments_path)

    def test_post_init_converts_str_to_path(self):
        downloader = DummyAudioParts(
            url=self.url,
            audio_title=self.audio_title,
            audiowork_dir=Path("/path/to/audio"),
        )
        self.assertIsInstance(downloader.audiowork_dir, Path)

    def test_prepare_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            downloader = DummyAudioParts(
                url=self.url,
                audio_title=self.audio_title,
                audiowork_dir=tmp_path / "audiowork",
            )
            downloader._prepare_directories()
            self.assertTrue(os.path.exists(downloader.audiowork_dir)) # type: ignore
            self.assertTrue(os.path.exists(downloader.segments_path)) # type: ignore

    def test_purge_chunks_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            segments_path = tmp_path / "segments"
            os.makedirs(segments_path)
            downloader = DummyAudioParts(
                url=self.url,
                audio_title=self.audio_title,
                segments_path=segments_path,
            )
            downloader._purge_chunks_dir()
            self.assertFalse(os.path.exists(segments_path))


if __name__ == "__main__":
    unittest.main()
