import os
import subprocess
import sys
import unittest
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from unittest import mock
from rich.progress import Progress

from crodl.exceptions import DownloadError
from crodl.streams import DASH, HLS, MP3
from crodl.streams.audioparts import (
    OPEN_FILE_LIMIT,
    AudioParts,
    _raise_open_file_limit,
)


@dataclass
class DummyAudioParts(AudioParts):
    """Minimal concrete downloader used by the tests."""

    extension: str = "aac"

    async def download(
        self, progress: Optional[Progress] = None, task_id: Optional[Any] = None
    ) -> None:
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
            self.assertTrue(os.path.exists(downloader.audiowork_dir))  # type: ignore
            self.assertTrue(os.path.exists(downloader.segments_path))  # type: ignore

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


class FakeResource:
    """Minimal stand-in for the `resource` module used in tests."""

    RLIMIT_NOFILE = 7
    RLIM_INFINITY = 2**63 - 1

    def __init__(self, soft: int, hard: int):
        self.limit = (soft, hard)
        self.set_calls: list[tuple] = []

    def getrlimit(self, _resource):
        return self.limit

    def setrlimit(self, _resource, limit):
        self.set_calls.append(limit)
        self.limit = limit


class TestRaiseOpenFileLimit(unittest.TestCase):
    def test_raises_soft_limit_when_hard_is_infinite(self):
        fake = FakeResource(soft=256, hard=FakeResource.RLIM_INFINITY)
        with mock.patch.dict(sys.modules, {"resource": fake}):
            _raise_open_file_limit()

        self.assertEqual(
            fake.set_calls, [(OPEN_FILE_LIMIT, FakeResource.RLIM_INFINITY)]
        )

    def test_caps_target_to_hard_limit(self):
        fake = FakeResource(soft=256, hard=1024)
        with mock.patch.dict(sys.modules, {"resource": fake}):
            _raise_open_file_limit()

        self.assertEqual(fake.set_calls, [(1024, 1024)])

    def test_does_not_lower_an_already_sufficient_limit(self):
        fake = FakeResource(soft=10000, hard=FakeResource.RLIM_INFINITY)
        with mock.patch.dict(sys.modules, {"resource": fake}):
            _raise_open_file_limit()

        self.assertEqual(fake.set_calls, [])

    def test_silently_skips_when_resource_module_is_missing(self):
        # Simulates Windows, where the `resource` module does not exist.
        with mock.patch.dict(sys.modules, {"resource": None}):
            _raise_open_file_limit()  # must not raise


class TestMergeChunks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.segments_path = self.tmp_path / "segments"
        self.audiowork_dir = self.tmp_path / "audiowork"
        os.makedirs(self.segments_path)
        os.makedirs(self.audiowork_dir)
        (self.segments_path / "list.txt").write_text("media_0.aac\n", encoding="utf-8")

        self.downloader = DummyAudioParts(
            url="http://example.com/audio.m3u8",
            audio_title="Test Audio",
            audiowork_dir=self.audiowork_dir,
            segments_path=self.segments_path,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_merge_chunks_raises_open_file_limit_and_runs_ffmpeg(self):
        with (
            mock.patch("crodl.streams.audioparts._raise_open_file_limit") as mock_limit,
            mock.patch("crodl.streams.audioparts.subprocess.run") as mock_run,
        ):
            self.downloader._merge_chunks()

        mock_limit.assert_called_once()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        command = args[0]
        self.assertIn("concatf:list.txt", command)
        self.assertEqual(command[-2], "error")  # loglevel, not quiet
        self.assertEqual(kwargs["cwd"], str(self.segments_path))
        self.assertTrue(kwargs["check"])

    def test_merge_chunks_raises_download_error_with_ffmpeg_detail(self):
        stderr = "\n".join(
            [
                "[in#0 @ 0x0] Error opening input: Too many open files",
                "Error opening input file concatf:list.txt.",
            ]
        )
        exc = subprocess.CalledProcessError(
            returncode=232, cmd=["ffmpeg"], stderr=stderr
        )
        with mock.patch("crodl.streams.audioparts.subprocess.run", side_effect=exc):
            with self.assertRaises(DownloadError) as ctx:
                self.downloader._merge_chunks()

        self.assertIn("exit code 232", str(ctx.exception))
        self.assertIn("Too many open files", str(ctx.exception))

    def test_merge_chunks_rejects_unsupported_format(self):
        downloader = DummyAudioParts(
            url="http://example.com/audio.ogg",
            audio_title="Test Audio",
            audiowork_dir=self.audiowork_dir,
            segments_path=self.segments_path,
            extension="ogg",
        )
        with self.assertRaises(ValueError):
            downloader._merge_chunks()

    def test_merge_chunks_removes_accents_from_output_name(self):
        downloader = DummyAudioParts(
            url="http://example.com/audio.m3u8",
            audio_title="Příliš žluťoučký kůň",
            audiowork_dir=self.audiowork_dir,
            segments_path=self.segments_path,
            remove_accents=True,
        )
        with (
            mock.patch("crodl.streams.audioparts._raise_open_file_limit"),
            mock.patch("crodl.streams.audioparts.subprocess.run") as mock_run,
        ):
            downloader._merge_chunks()

        command = mock_run.call_args.args[0]
        output = next(arg for arg in command if arg.endswith(".aac"))
        self.assertTrue(output.endswith("Prilis zlutoucky kun.aac"), output)


class TestDownloaderExtensions(unittest.TestCase):
    """
    Every downloader must declare the container it produces.

    Regression: HLS/DASH used to inherit the empty default, so `_merge_chunks()`
    failed with "Format '' is not supported!" only when a real download ran.
    """

    def test_declared_extensions(self):
        self.assertEqual(MP3.extension, "mp3")
        self.assertEqual(HLS.extension, "aac")
        self.assertEqual(DASH.extension, "m4a")

    def test_merge_chunks_writes_the_extension_of_each_downloader(self):
        # Only HLS and DASH go through ffmpeg; MP3 is downloaded as one file
        # (and "mp3" is deliberately not in SUPPORTED_AUDIO_FORMATS).
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            downloaders = [
                HLS(url="https://example.com/playlist.m3u8", audio_title="Titul"),
                DASH(url="https://example.com/manifest.mpd", audio_title="Titul"),
            ]

            for downloader in downloaders:
                downloader.audiowork_dir = folder
                downloader.segments_path = folder

                with (
                    mock.patch("crodl.streams.audioparts._raise_open_file_limit"),
                    mock.patch("crodl.streams.audioparts.subprocess.run") as mock_run,
                ):
                    downloader._merge_chunks()

                command = mock_run.call_args.args[0]
                output = next(
                    arg for arg in command if arg.endswith(f".{downloader.extension}")
                )
                self.assertTrue(
                    output.endswith(f"Titul.{downloader.extension}"),
                    f"{type(downloader).__name__} wrote {output}",
                )


if __name__ == "__main__":
    unittest.main()
