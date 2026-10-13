"""The whole download path: format dispatch -> segments -> merge -> the hook.

`tests/test_audiowork.py` mocks the downloaders away and `tests/test_audioparts.py`
checks the merge on its own; only an end-to-end run shows the wiring *between*
them, which is where the missing-extension bug slipped through: HLS and DASH
never declared a container, so ffmpeg was asked to write a file with no name at
all - and that only surfaced during a real download.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crodl.program.audiowork import AudioWork
from crodl.streams.dash import DASH
from crodl.streams.hls import HLS

CHUNKLIST = (
    "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\nmedia_0.aac\nmedia_1.aac\n"
)

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
  <Period>
    <AdaptationSet mimeType="audio/mp4">
      <Representation id="42" bandwidth="128000">
        <SegmentList timescale="1000" duration="10">
          <SegmentTimeline><S d="10" r="1"/></SegmentTimeline>
        </SegmentList>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
"""


class Ffmpeg:
    """Stands in for ffmpeg: records what it was asked to merge, writes the file."""

    def __init__(self) -> None:
        # What the merge was pointed at (list.txt) and what it produced.
        self.listings: list[list[str]] = []
        self.outputs: list[str] = []

    def __call__(self, command, cwd=None, **kwargs):
        self.listings.append(
            (Path(cwd) / "list.txt").read_text(encoding="utf-8").split()
        )

        output = Path(command[5])
        self.outputs.append(output.name)
        output.write_bytes(b"merged")

        return mock.Mock(returncode=0)


async def segments_writer(urls, target_folder, progress_callback=None):
    """Stands in for the HTTP part: writes whatever was requested."""
    for url in urls:
        (Path(target_folder) / url.rsplit("/", 1)[-1]).write_bytes(b"segment")
        if progress_callback:
            progress_callback()


def recorded_into(recorded: list[Path]):
    """The hook `AudioWork` reports a finished file to."""

    async def hook(work, path, collection=None):
        recorded.append(path)

    return hook


def make_work(directory: Path, variant: str, url: str) -> AudioWork:
    """A loaded work whose only audio link is the given variant."""
    client = mock.Mock()
    client.session = mock.Mock()
    client.get_episode_data.return_value = {
        "data": {
            "attributes": {
                "title": "Díl",
                "since": "2024-08-14T18:05:00+02:00",
                "audioLinks": [{"variant": variant, "url": url}],
            }
        }
    }
    return AudioWork(uuid="12345", title="Díl", audiowork_dir=directory, client=client)


class TestHlsDownload(unittest.IsolatedAsyncioTestCase):
    async def test_chunklist_chunks_are_merged_into_one_aac(self):
        ffmpeg = Ffmpeg()
        recorded: list[Path] = []

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            with (
                mock.patch.object(
                    HLS,
                    "_get_chunklist_m3u8",
                    lambda self: self.chunklist_path.write_text(
                        CHUNKLIST, encoding="utf-8"
                    ),
                ),
                mock.patch("crodl.streams.hls.download_parts", new=segments_writer),
                mock.patch("crodl.streams.audioparts.subprocess.run", new=ffmpeg),
            ):
                await make_work(
                    directory, "hls", "https://example.com/playlist.m3u8"
                ).download(on_downloaded=recorded_into(recorded))

            self.assertEqual(recorded, [directory / "Díl.aac"])
            self.assertEqual(ffmpeg.outputs, ["Díl.aac"])
            # The chunk names of the chunklist are what ffmpeg concatenates.
            self.assertEqual(ffmpeg.listings, [["media_0.aac", "media_1.aac"]])
            self.assertEqual((directory / "Díl.aac").read_bytes(), b"merged")
            # The segment folder is temporary: it must not survive the download.
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ["Díl.aac"])


class TestDashDownload(unittest.IsolatedAsyncioTestCase):
    async def test_segments_are_renamed_sorted_and_merged_into_one_m4a(self):
        ffmpeg = Ffmpeg()
        recorded: list[Path] = []

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            with (
                mock.patch.object(
                    DASH,
                    "_get_manifest",
                    lambda self: self.manifest_path.write_bytes(MANIFEST.encode()),
                ),
                mock.patch("crodl.streams.dash.download_parts", new=segments_writer),
                mock.patch("crodl.streams.audioparts.subprocess.run", new=ffmpeg),
            ):
                await make_work(
                    directory, "dash", "https://example.com/manifest.mpd"
                ).download(on_downloaded=recorded_into(recorded))

            self.assertEqual(recorded, [directory / "Díl.m4a"])
            self.assertEqual(ffmpeg.outputs, ["Díl.m4a"])
            # The init segment comes first, then the media segments in order.
            self.assertEqual(ffmpeg.listings, [["cinit.m4s", "0.m4s", "10.m4s"]])
            self.assertEqual((directory / "Díl.m4a").read_bytes(), b"merged")
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ["Díl.m4a"])


class TestMp3Download(unittest.IsolatedAsyncioTestCase):
    async def test_the_file_is_written_where_the_work_expects_it(self):
        response = mock.Mock()
        response.status = 200
        response.headers = {"Content-Length": "11"}
        response.content.iter_chunked = lambda size: self._chunks()
        recorded: list[Path] = []

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            with mock.patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = response
                await make_work(
                    directory, "mp3", "https://example.com/file.mp3"
                ).download(on_downloaded=recorded_into(recorded))

            self.assertEqual(recorded, [directory / "Díl.mp3"])
            self.assertEqual((directory / "Díl.mp3").read_bytes(), b"audio-bytes")

    @staticmethod
    async def _chunks():
        yield b"audio-bytes"


if __name__ == "__main__":
    unittest.main()
