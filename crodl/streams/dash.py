import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from bs4 import BeautifulSoup
from rich.progress import Progress

from crodl.streams.audioparts import AudioParts
from crodl.streams.download import download_parts
from crodl.streams.utils import (
    audio_segment_sort,
    get_m4a_url,
    partial_sums,
    simplify_audio_name,
    shorten_title,
)
from crodl.tools.logger import crologger
from crodl.settings import TIMEOUT


def get_m4s_segment_url(
    audio_link: str,
    repr_id: str,
    segment_time: str | int | None = None,
    init: bool = False,
) -> str:
    """
    Get the segment URL for a given audio link and representation ID.
    """
    m4a_url = get_m4a_url(audio_link)

    if init:
        return f"{m4a_url}/segment_ctaudio_rid{repr_id}_cinit_mpd.m4s"

    return f"{m4a_url}/segment_ctaudio_rid{repr_id}_cs{segment_time}_mpd.m4s"


def audio_segment_times(mpd_content: BeautifulSoup) -> list[int]:
    """
    Return a list of stream segment times extracted from the MPD content.
    """
    segment_times = []
    for s_tag in mpd_content.find_all("S"):
        duration = int(s_tag["d"])  # type: ignore
        repeat = int(s_tag.get("r", 0))  # type: ignore
        segment_times.extend([duration] * (repeat + 1))  # type: ignore

    return segment_times


def segments_info(manifest_content: str) -> tuple[list[int], str]:
    """
    Retrieve information about segments from the provided MPD Manifest file.
    """
    soup = BeautifulSoup(manifest_content, "xml")
    representation = soup.find("Representation", id=True)

    if not representation:
        raise KeyError("Block 'representation' not found.")

    representation_id = representation.get("id")  # type: ignore
    d_values = audio_segment_times(soup)

    return partial_sums(d_values), str(representation_id)


def segments_urls(manifest: "DASH") -> list[str]:
    """
    Generate a list of segment URLs for the given MPD URL.
    """
    segment_times, id_ = segments_info(manifest.content)
    init_chunk = get_m4s_segment_url(manifest.url, id_, init=True)
    zeroth_chunk = get_m4s_segment_url(manifest.url, id_, 0)

    return (
        [init_chunk]
        + [zeroth_chunk]
        + [
            get_m4s_segment_url(manifest.url, id_, segment_time)
            for segment_time in segment_times
        ][:-1]
    )


@dataclass
class DASH(AudioParts):
    """Processes a DASH stream using its manifest file."""

    @property
    def manifest_path(self) -> Path:
        """Path to the manifest file"""
        if not self.segments_path:
            raise ValueError("Segments Path is not set!")
        return self.segments_path / "manifest.mpd"

    def _get_manifest(self) -> None:
        """Fetches the manifest and saves it to a file locally."""
        from requests import Session

        session = self.session or Session()

        mp4_url = get_m4a_url(self.url)
        manifest_url = mp4_url + "/manifest.mpd"
        _manifest = session.get(manifest_url, timeout=TIMEOUT)

        with open(self.manifest_path, "wb") as f:
            f.write(_manifest.content)

    @property
    def content(self) -> str:
        """Manifest content"""
        if not os.path.isfile(self.manifest_path):
            self._get_manifest()

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return f.read()

    @property
    def id(self) -> str:
        """Audiowork ID in manifest.mpd"""
        repr_id = segments_info(self.content)[1]
        if repr_id and isinstance(repr_id, str):
            return repr_id

        raise ValueError("Representation ID not found.")

    @property
    def segment_urls(self) -> list[str]:
        """Return segment urls (urls of all audio segments)"""
        return segments_urls(self)

    def create_list_txt(self) -> None:
        """Creates a sorted list of all audio segment names (processed) and saves it to list.txt"""
        if not self.segments_path:
            raise ValueError("Segments Path is not set!")

        segment_names = list(os.listdir(self.segments_path))

        if not segment_names or all(
            not segment.endswith(".m4s") for segment in segment_names
        ):
            raise ValueError("Cannot create an audio file. Segments not found.")

        simplified_names = [
            simplify_audio_name(self.id, name)
            for name in segment_names
            if "init" not in name and name.endswith(".m4s")
        ]

        sorted_names = sorted(simplified_names, key=audio_segment_sort)
        sorted_names.insert(0, "cinit.m4s")

        list_path = self.segments_path / "list.txt"
        with list_path.open("w", encoding="utf-8") as segment:
            for name in sorted_names:
                segment.write(f"{name}\n")

    def rename_segments(self) -> None:
        """Simplifies / renames audio segments."""
        if not self.segments_path:
            raise ValueError("Segments Path is not set!")

        for segment in os.listdir(self.segments_path):
            if segment.startswith("segment_"):
                new_name = simplify_audio_name(self.id, segment)
                os.rename(
                    self.segments_path / segment,
                    self.segments_path / new_name,
                )

    async def download(
        self, progress: Optional[Progress] = None, task_id: Optional[Any] = None
    ):
        """
        Asynchronously downloads chunk files using the segment URLs
        and saves them to the specified segments path.
        """
        self._prepare_directories()

        if not self.segments_path:
            raise ValueError("Segments Path is not set!")

        urls = self.segment_urls
        if progress:
            if task_id is None:
                task_id = progress.add_task(
                    shorten_title(self.audio_title, 20), total=len(urls)
                )
            await download_parts(
                urls,
                self.segments_path,
                progress_callback=lambda: progress.update(task_id, advance=1),
            )
        else:
            with Progress() as internal_progress:
                task_id = internal_progress.add_task(
                    shorten_title(self.audio_title, 20), total=len(urls)
                )
                await download_parts(
                    urls,
                    self.segments_path,
                    progress_callback=lambda: internal_progress.update(
                        task_id, advance=1
                    ),
                )

        crologger.info("Processing segments...")
        self.rename_segments()
        self.create_list_txt()

        self._merge_chunks("m4a")
        self._purge_chunks_dir()
        crologger.info("DASH download completed.")
