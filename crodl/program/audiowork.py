import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

from rich.progress import Progress

from crodl.data.attributes import extract_asset_url, extract_parent
from crodl.program.content import Collection, Content, DownloadedHook
from crodl.settings import DOWNLOAD_PATH, PREFERRED_AUDIO_FORMAT, AudioFormat
from crodl.streams import DASH, HLS, MP3, AudioParts
from crodl.streams.utils import (
    create_dir_if_does_not_exist,
    get_preferred_audio_format,
    not_available_yet,
    process_audiowork_title,
    remove_html_tags,
)
from crodl.tools.logger import crologger


@dataclass
class AudioWork(Content):
    """
    Processes the audiowork at given URL or by its UUID.
    Focuses on downloading audio content.
    """

    audiowork_dir: Optional[Path] = None
    audiowork_root: Optional[Path] = None
    since: str = ""
    series: bool = False
    show: bool = False
    remove_accents: bool = False
    _attrs: Dict[str, Any] = field(default_factory=dict, repr=False)
    json_data: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.url and self.uuid:
            err_msg = "Audio cannot be defined by both url and uuid!"
            crologger.error(err_msg)
            raise ValueError(err_msg)

        if not self.url and not self.uuid:
            err_msg = "Audio must be defined by either url or uuid!"
            crologger.error(err_msg)
            raise ValueError(err_msg)

        self._apply_data()

    def _apply_data(self) -> None:
        """Derives the fields that depend on the (possibly injected) API data."""
        if not self._attrs:
            try:
                self._attrs = self.json_data.get("data", {}).get("attributes", {})
            except (AttributeError, TypeError):
                self._attrs = {}

        # Use custom title if provided, otherwise fallback to API title
        if self.title == "Unknown" or not self.title:
            self.title = str(self._attrs.get("title", "Unknown"))

        # Determine download directory (only once the title is known)
        if not self.audiowork_dir and self.title not in ("", "Unknown"):
            self.audiowork_dir = DOWNLOAD_PATH / process_audiowork_title(
                self.title, remove_accents=self.remove_accents
            )

        if not self.audiowork_root:
            self.audiowork_root = self.audiowork_dir

        if not self.since:
            self.since = str(self._attrs.get("since", ""))

    async def load(self) -> None:
        """
        Fetches the episode data from the API. Safe to call repeatedly.

        Construction is deliberately free of I/O, so the API-derived fields
        are only reliable after this has been awaited.
        """
        if self.loaded:
            return

        if not self.uuid:
            self.uuid = self.client.get_audio_uuid(self.url) if self.url else None

        if not self.json_data and self.uuid:
            self.json_data = self.client.get_episode_data(self.uuid)

        self._apply_data()
        self.loaded = True

    @property
    def audio_links(self) -> list[dict] | None:
        audio_links = self._attrs.get("audioLinks")

        if audio_links:
            return audio_links

        crologger.error(self.title)
        crologger.error("Link not found. This episode is not available.")

        return None

    @property
    def unavailable_reason(self) -> str:
        """Explains why a work without any audio link cannot be downloaded."""
        return not_available_yet(self)

    @property
    def audio_formats(self) -> list[str] | None:
        audio_variants: list[str] = []
        if self.audio_links and isinstance(self.audio_links, list):
            for link in self.audio_links:
                variant = link.get("variant")
                if variant:
                    audio_variants.append(str(variant))

        return audio_variants or None

    @property
    def audio_formats_urls(self) -> dict[str | None, str | None]:
        """URLs of various audio formats"""
        if self.audio_links and isinstance(self.audio_links, list):
            return {link.get("variant"): link.get("url") for link in self.audio_links}
        return {}

    @property
    def description(self) -> str | None:
        if not self._attrs:
            return None

        desc = self._attrs.get("description")
        if desc:
            return remove_html_tags(str(desc))
        return None

    @property
    def author(self) -> str | None:
        """Author/interpret as reported by the API, if it provides one."""
        for key in ("author", "interpret", "artist"):
            value = self._attrs.get(key)
            if value:
                return str(value)
        return None

    @property
    def parent(self) -> tuple[str, str] | None:
        """
        The show or serial this episode was aired in, if the API names one.

        A one-off episode is a work of its own, but it was aired inside a
        magazine show - the library files its file under that work instead of
        leaving it among the files that belong to nothing.
        """
        return extract_parent(self.json_data or {})

    @property
    def asset_url(self) -> str | None:
        """URL of the work's artwork (thumbnail), if the API provides one."""
        return extract_asset_url(self._attrs)

    @property
    def short_title(self) -> str | None:
        """The API's short title for the work, if it provides one."""
        value = self._attrs.get("shortTitle")
        return str(value) if value else None

    @property
    def part(self) -> int | None:
        """Episode number inside its series/show, as reported by the API."""
        value = self._attrs.get("part")
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def duration(self) -> int | None:
        """Duration of the first audio variant in seconds, if the API reports it."""
        for link in self.audio_links or []:
            value = link.get("duration")
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    def info(self) -> list[dict]:
        """
        Returns the available audio variants of the work.

        Formatting (duration, size) is left to the caller so that the core
        stays free of presentation.
        """
        audio_links = self._attrs.get("audioLinks") or []
        return [
            {
                "variant": link.get("variant"),
                "bitrate": link.get("bitrate"),
                "duration_seconds": link.get("duration"),
                "size_bytes": link.get("sizeInBytes"),
            }
            for link in audio_links
        ]

    def already_exists(self) -> bool:
        """Checks whether the audiowork already exists on disk."""
        if not self.audiowork_dir:
            return False

        try:
            files_in_directory = os.listdir(self.audiowork_dir)
        except FileNotFoundError:
            files_in_directory = []

        # The downloaders write exactly `process_audiowork_title(title) + ext`,
        # so compare the full stem instead of a substring (which could match
        # e.g. "13 - Title" while looking for "3 - Title").
        expected_stem = process_audiowork_title(
            self.title, remove_accents=self.remove_accents
        )
        return any(
            os.path.splitext(file)[0] == expected_stem for file in files_in_directory
        )

    async def _download_dash(
        self, progress: Optional[Progress] = None, task_id: Optional[Any] = None
    ) -> DASH:
        """Download DASH stream."""
        mpd_url = self.audio_formats_urls.get("dash")
        if not mpd_url:
            raise ValueError("DASH Manifest URL not found.")

        if not self.audiowork_dir:
            raise ValueError("audiowork_dir is not set.")

        manifest = DASH(
            url=mpd_url,
            audio_title=self.title,
            audiowork_dir=self.audiowork_dir,
            session=self.client.session,
            remove_accents=self.remove_accents,
        )
        await manifest.download(progress=progress, task_id=task_id)
        return manifest

    async def _download_hls(
        self, progress: Optional[Progress] = None, task_id: Optional[Any] = None
    ) -> HLS:
        """Download HLS stream."""
        hls_url = self.audio_formats_urls.get("hls")
        if not hls_url:
            raise ValueError("HLS chunklist.txt URL not found.")

        if not self.audiowork_dir:
            raise ValueError("audiowork_dir is not set.")

        chunklist = HLS(
            url=hls_url,
            audio_title=self.title,
            audiowork_dir=self.audiowork_dir,
            session=self.client.session,
            remove_accents=self.remove_accents,
        )
        await chunklist.download(progress=progress, task_id=task_id)
        return chunklist

    async def _download_mp3(
        self, progress: Optional[Progress] = None, task_id: Optional[Any] = None
    ) -> MP3:
        """Download MP3 file."""
        mp3_url = self.audio_formats_urls.get("mp3")
        if not mp3_url:
            raise ValueError("MP3 file URL not found.")

        if not self.audiowork_dir:
            raise ValueError("audiowork_dir is not set.")

        mp3 = MP3(
            url=mp3_url,
            audiowork_dir=self.audiowork_dir,
            audio_title=self.title,
            segments=False,
            session=self.client.session,
            remove_accents=self.remove_accents,
        )
        await mp3.download(progress=progress, task_id=task_id)
        return mp3

    async def download(
        self,
        audio_format: Optional[AudioFormat] = PREFERRED_AUDIO_FORMAT,
        progress: Optional[Progress] = None,
        task_id: Optional[Any] = None,
        on_downloaded: Optional[DownloadedHook] = None,
        collection: Optional[Collection] = None,
    ) -> None:
        """Downloads audio and handles storage."""
        await self.load()

        if not self.audio_formats:
            return

        selected_format = audio_format
        if selected_format and selected_format.value not in self.audio_formats:
            crologger.info(
                "Format %s not available, searching for alternative...",
                selected_format.value,
            )
            selected_format = get_preferred_audio_format(self.audio_formats)

        if not self.audiowork_dir:
            raise ValueError("audiowork_dir is not set.")

        if not self.already_exists():
            if not self.series and not self.show:
                create_dir_if_does_not_exist(self.audiowork_dir)

            downloader: Optional[AudioParts] = None
            match selected_format:
                case AudioFormat.DASH:
                    downloader = await self._download_dash(
                        progress=progress, task_id=task_id
                    )
                case AudioFormat.HLS:
                    downloader = await self._download_hls(
                        progress=progress, task_id=task_id
                    )
                case AudioFormat.MP3:
                    downloader = await self._download_mp3(
                        progress=progress, task_id=task_id
                    )
                case None:
                    crologger.error("No valid format found for: %s", self.title)
                    return

            if on_downloaded is not None and downloader is not None:
                await on_downloaded(self, downloader.output_path, collection)

            crologger.info("Done.")

        else:
            if progress and task_id:
                progress.update(
                    task_id,
                    description=f"[cyan]{self.title} (existuje)[/cyan]",
                    completed=1,
                    total=1,
                )

            crologger.info("%s already exists.", self.title)
