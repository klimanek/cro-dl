import os
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from yaspin import yaspin

from crodl.streams.audioparts import AudioParts
from crodl.streams.download import download_parts
from crodl.streams.utils import (
    audio_segment_sort,
    get_m4a_url,
    partial_sums,
    simplify_audio_name,
)


def get_m4s_segment_url(
    audio_link: str,
    repr_id: str,
    segment_time: str | int | None = None,
    init: bool = False,
) -> str:
    """
    Get the segment URL for a given audio link and representation ID.

    Args:
        audio_link (str): The URL of the audio.
        repr_id (str): The representation ID.
        segment_time (str | int | None, optional): The segment time. Defaults to None.
        init (bool, optional): Whether it is an initial segment. Defaults to False.

    Returns:
        str | None: The segment URL if it exists, else None.
    """
    m4a_url = get_m4a_url(audio_link)

    if init:
        return f"{m4a_url}/segment_ctaudio_rid{repr_id}_cinit_mpd.m4s"

    return f"{m4a_url}/segment_ctaudio_rid{repr_id}_cs{segment_time}_mpd.m4s"


def audio_segment_times(mpd_content: BeautifulSoup) -> list[int]:
    """
    Return a list of stream segment times extracted from the MPD content.

    Args:
        mpd_content (BeautifulSoup): The parsed MPD content.

    Returns:
        list[int]: A list of segment times.
    """

    segment_times = []
    for s_tag in mpd_content.find_all("S"):
        duration = int(s_tag["d"])  # type: ignore

        # Default to 0 if 'r' attribute is not present
        repeat = int(s_tag.get("r", 0))  # type: ignore

        # Repeat 'r' times
        segment_times.extend([duration] * (repeat + 1))  # type: ignore

    return segment_times


def segments_info(manifest_content: str) -> tuple[list[int], str]:
    """
    Retrieve information about segments from the provided MPD Manifest file.

    Args:
        manifest_content (str): MPD file content.

    Returns:
        list[str]: A list containing the partial sums of d_values and the representation ID.
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

    Args:
        manifest_content (str): The content of the MPD file.

    Returns:
        list[str]: A list of segment URLs.

    Example:
        [
        'https://example.com/stream/xyz.m4a/audio_09876abc_cinit_mpd.m4s', # initial segment
        'https://example.com/stream/xyz.m4a/audio_09876abc_cs0_mpd.m4s', # zeroth segment
        'https://example.com/stream/xyz.m4a/audio_09876abc_cs480240_mpd.m4s', # first segment
        'https://example.com/stream/xyz.m4a/audio_09876abc_cs960528_mpd.m4s',
        'https://example.com/stream/xyz.m4a/audio_09876abc_cs1439760_mpd.m4s',
        'https://example.com/stream/xyz.m4a/audio_09876abc_cs1920000_mpd.m4s',
        ...
        ]
    """
    segment_times, id_ = segments_info(manifest.content)
    init_chunk = get_m4s_segment_url(manifest.url, id_, init=True)
    zeroth_chunk = get_m4s_segment_url(manifest.url, id_, 0)

    # The last segment is not included in the list, according to DASH specification.
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
    def manifest_path(self) -> Path:  # pragma: no cover
        """Path to the manifest file"""
        if not self.segments_path:
            raise ValueError("Segments Path is not set!")
        return self.segments_path / "manifest.mpd"

    def _get_manifest(self) -> None:
        """Fetches the manifest and saves it to a file locally."""
        from crodl.tools.scrap import cro_session

        mp4_url = get_m4a_url(self.url)
        manifest_url = mp4_url + "/manifest.mpd"
        _manifest = cro_session.get(manifest_url, timeout=5)

        with open(self.manifest_path, "wb") as f:
            f.write(_manifest.content)

    @property
    def content(self) -> str:  # pragma: no cover
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
        segment_names = list(os.listdir(self.segments_path))

        if not segment_names or all(
            not segment.endswith(".m4s") for segment in segment_names
        ):
            raise ValueError("Cannot create an audio file. Segments not found.")

        simplified_names = [
            simplify_audio_name(self.id, name)
            for name in segment_names
            if "init" not in name
        ]

        sorted_names = sorted(simplified_names, key=audio_segment_sort)
        sorted_names.insert(0, "cinit.m4s")

        # Write the segment names to list.txt
        if not self.segments_path:
            raise ValueError("Segments Path is not set!")
        if not isinstance(self.segments_path, Path):
            self.segments_path = Path(self.segments_path)

        list_path = self.segments_path / "list.txt"
        with list_path.open("w", encoding="utf-8") as segment:
            for name in sorted_names:
                segment.write(f"{name}\n")

    def rename_segments(self) -> None:  # pragma: no cover
        """Simplifies / renames audio segments."""
        for segment in os.listdir(self.segments_path):
            if segment.startswith("segment_"):
                new_name = simplify_audio_name(self.id, segment)

                if not self.segments_path:
                    raise ValueError("Segments Path is not set!")

                os.rename(
                    self.segments_path / segment,
                    self.segments_path / new_name,
                )

    async def download(self):  # pragma: no cover
        """
        Asynchronously downloads chunk files using the segment URLs
        and saves them to the specified segments path.

        After the download is completed, merging is run and, finally,
        the tmp dir with chunks is deleted.
        """
        if not self.segments_path:
            raise ValueError("Segments Path is not set!")

        with yaspin(text=f"Stahuji {self.audio_title}", color="yellow") as _:
            await download_parts(self.segment_urls, self.segments_path)

        with yaspin(text=f"Zpracovávám {self.audio_title}", color="yellow") as _:
            self.create_list_txt()
            self.rename_segments()

        self._merge_chunks("m4a")
        self._purge_chunks_dir()
