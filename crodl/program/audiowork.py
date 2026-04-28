import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

from rich import print
from rich.progress import Progress

from crodl.data.streamlinks import StreamLinks
from crodl.program.content import Content
from crodl.settings import DOWNLOAD_PATH, PREFERRED_AUDIO_FORMAT, AudioFormat
from crodl.streams import DASH, HLS, MP3
from crodl.streams.utils import (
    HMS,
    create_dir_if_does_not_exist,
    file_size,
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

        if not self.uuid:
            self.uuid = self.client.get_audio_uuid(self.url) if self.url else None

        if not self.json_data and self.uuid:
            self.json_data = self.client.get_episode_data(self.uuid)

        if not self._attrs:
            try:
                self._attrs = self.json_data.get("data", {}).get("attributes", {})
            except (AttributeError, TypeError):
                self._attrs = {}

        # Use custom title if provided, otherwise fallback to API title
        if self.title == "Unknown" or not self.title:
            self.title = str(self._attrs.get("title", "Unknown"))

        # Determine download directory
        if not self.audiowork_dir:
            self.audiowork_dir = (
                DOWNLOAD_PATH / process_audiowork_title(self.title, remove_accents=self.remove_accents)
            )

        if not self.audiowork_root:
            self.audiowork_root = self.audiowork_dir

        if not self.since:
            self.since = str(self._attrs.get("since", ""))

    @property
    def audio_links(self) -> list[dict] | None:
        audio_links = self._attrs.get("audioLinks")

        if audio_links:
            return audio_links

        print(f"❌ {self.title}")
        err = "Link not found. This episode is not available."
        crologger.error(self.title)
        crologger.error(err)

        not_yet = not_available_yet(self)
        print(not_yet)

        return None

    @property
    def audio_formats(self) -> list[str] | None:
        audio_variants = []
        if self.audio_links and isinstance(self.audio_links, list):
            for link in self.audio_links:
                if link.get("variant"):
                    audio_variants.append(link.get("variant"))

        if audio_variants and isinstance(audio_variants, list):
            return audio_variants

        return None

    @property
    def audio_formats_urls(self) -> dict[str | None, str | None]:
        """URLs of various audio formats"""
        if self.audio_links and isinstance(self.audio_links, list):
            return {link.get("variant"): link.get("url") for link in self.audio_links}
        return {}

    @property
    def links(self):
        audio_links = StreamLinks()
        for key, val in self.audio_formats_urls.items():
            if key:
                setattr(audio_links, key, val)

        return audio_links

    @property
    def description(self) -> str | None:
        if not self._attrs:
            return None

        desc = self._attrs.get("description")
        if desc:
            return remove_html_tags(str(desc))
        return None

    def info(self):
        """Display basic info about the audio work."""
        attrs = self._attrs
        audio_links = attrs.get("audioLinks", [])

        print(f"\n[bold yellow]{self.title}[/bold yellow]")
        for alink in audio_links:
            bitrate = alink.get("bitrate")
            duration = alink.get("duration")
            size = alink.get("sizeInBytes", "Stream")
            variant = alink.get("variant")

            print(f"- {HMS(duration)} - {file_size(size)} - {bitrate} kbps - {variant}")

        print(f"\n[blue]{self.description}[/blue]\n")

    def already_exists(self) -> bool:  # pragma: no cover
        """Checks whether the audiowork already exists on disk."""
        if not self.audiowork_dir:
            return False
            
        try:
            files_in_directory = os.listdir(self.audiowork_dir)
        except FileNotFoundError:
            files_in_directory = []

        if files_in_directory:
            processed_title = process_audiowork_title(self.title, remove_accents=self.remove_accents)
            for file in files_in_directory:
                if processed_title in os.path.splitext(file)[0]:
                    return True
        return False

    async def _download_dash(self, progress: Optional[Progress] = None, task_id: Optional[Any] = None) -> None:
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
        )
        await manifest.download(progress=progress, task_id=task_id)

    async def _download_hls(self, progress: Optional[Progress] = None, task_id: Optional[Any] = None) -> None:
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
        )
        await chunklist.download(progress=progress, task_id=task_id)

    async def _download_mp3(self, progress: Optional[Progress] = None, task_id: Optional[Any] = None):
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
        )
        await mp3.download(progress=progress, task_id=task_id)

    async def download(
        self, 
        audio_format: Optional[AudioFormat] = PREFERRED_AUDIO_FORMAT,
        progress: Optional[Progress] = None,
        task_id: Optional[Any] = None
    ) -> None:  # pragma: no cover
        """Downloads audio and handles storage."""
        if not self.audio_formats:
            return

        selected_format = audio_format
        if selected_format and selected_format.value not in self.audio_formats:
            crologger.info("Format %s not available, searching for alternative...", selected_format.value)
            selected_format = get_preferred_audio_format(self.audio_formats)

        if not self.audiowork_dir:
            raise ValueError("audiowork_dir is not set.")

        if not self.already_exists():
            if not self.series and not self.show:
                create_dir_if_does_not_exist(self.audiowork_dir)

            match selected_format:
                case AudioFormat.DASH:
                    await self._download_dash(progress=progress, task_id=task_id)
                case AudioFormat.HLS:
                    await self._download_hls(progress=progress, task_id=task_id)
                case AudioFormat.MP3:
                    await self._download_mp3(progress=progress, task_id=task_id)
                case None:
                    crologger.error("No valid format found for: %s", self.title)
                    return

            crologger.info("Done.")

        else:
            if progress and task_id:
                progress.update(task_id, description=f"[cyan]{self.title} (existuje)[/cyan]", completed=1, total=1)
            else:
                print(f"{self.title} již existuje.")
            
            crologger.info("%s already exists.", self.title)
