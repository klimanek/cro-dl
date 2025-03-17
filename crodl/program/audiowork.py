import os

from typing import Optional
from rich import print

from crodl.streams import DASH
from crodl.streams import HLS
from crodl.streams import MP3
from crodl.streams.utils import (
    HMS,
    file_size,
    get_preferred_audio_format,
    not_available_yet,
    process_audiowork_title,
    create_dir_if_does_not_exist,
    remove_html_tags,
)
from crodl.tools.logger import crologger
from crodl.tools.scrap import cro_session, get_attributes, get_audio_uuid
from crodl.settings import DOWNLOAD_PATH, PREFERRED_AUDIO_FORMAT, AudioFormat


class AudioWork:
    """
    Processes the audiowork at given URL or by its UUID.

    Args:
        url (str) -- URL of a website with audiowork "hidden" in e.g.:
            https://www.mujrozhlas.cz/hra-na-sobotu/ondrej-neff-velka-solarni-v-nervy-drasajicim-zavode-kosmickych-lodi-jde-doslova-o

        uuid (str) -- Unique ID of the audiowork.
    """

    def __init__(self, **kwargs) -> None:
        _url = kwargs.pop("url", None)
        _uuid = kwargs.pop("uuid", None)
        _title = kwargs.pop("title", None)
        _audiowork_dir = kwargs.pop("audiowork_dir", None)
        _audiowork_root = kwargs.pop("audiowork_root", None)
        _since = kwargs.pop("since", "")

        if _url and _uuid:
            _err_msg = "Audio cannot be defined by both url and uuid!"
            crologger.error(_err_msg)
            raise ValueError(_err_msg)

        if not _url and not _uuid:
            _err_msg = "Audio must be defined by either url or uuid!"
            crologger.error(_err_msg)
            raise ValueError(_err_msg)

        self.url = _url
        self.uuid = _uuid if _uuid else get_audio_uuid(self.url, cro_session)
        self._attrs = get_attributes(self.uuid, cro_session)

        if not _title:
            self.title = self._attrs.get("title", "Unknown")
        else:
            self.title = _title

        if _audiowork_dir:
            self.audiowork_dir = _audiowork_dir
        else:
            self.audiowork_dir = DOWNLOAD_PATH / process_audiowork_title(self.title)

        if _audiowork_root:
            self.audiowork_root = _audiowork_root
        else:
            self.audiowork_root = self.audiowork_dir

        self.series: bool = kwargs.pop("series", False)
        self.show: bool = kwargs.pop("show", False)

        self.since = _since if _since else self._attrs["since"]

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

    def info(self):
        """Some basic info on the file being downloaded."""
        attrs = self._attrs
        _description = attrs.get("description")
        _audio_links = attrs["audioLinks"]

        print(f"\n[bold yellow]{self.title}[/bold yellow]")
        for alink in _audio_links:
            bitrate = alink["bitrate"]
            duration = alink["duration"]
            size = alink.get("sizeInBytes", "Stream")
            variant = alink["variant"]

            print(
                f"+++ {HMS(duration)} +++ {file_size(size)} +++ {bitrate} kbps +++ {variant}"
            )

        print(f"\n[blue]{remove_html_tags(_description)}[/blue]\n")

    def already_exists(self) -> bool:  # pragma: no cover
        """Checks whether the audiowork already exists in the download directory."""
        # Get a list of all files in the audiowork directory
        try:
            files_in_directory = os.listdir(self.audiowork_dir)
        except FileNotFoundError:
            files_in_directory = []

        if files_in_directory:
            for file in files_in_directory:
                # Check if the file name matches the provided title (without extension)
                if process_audiowork_title(self.title) in os.path.splitext(file)[0]:
                    return True
        return False

    async def _download_dash(self) -> None:  # pragma: no cover
        """Download audio file from DASH stream
        (m4s segments -> m4a using its manifest.mpd file.)"""
        mpd_url = self.audio_formats_urls.get("dash")

        if not mpd_url:
            raise ValueError("DASH Manifest URL not found.")

        manifest = DASH(
            url=mpd_url, audio_title=self.title, audiowork_dir=self.audiowork_dir
        )

        await manifest.download()

    async def _download_hls(self) -> None:  # pragma: no cover
        """Download audio file from HLS stream
        (aac chunks -> aac file, using its chunklist)."""
        hls_url = self.audio_formats_urls.get("hls")

        if not hls_url:
            raise ValueError("HLS chunklist.txt URL not found.")

        chunklist = HLS(
            url=hls_url, audio_title=self.title, audiowork_dir=self.audiowork_dir
        )
        await chunklist.download()

    def _download_mp3(self):  # pragma: no cover
        """Download mp3 file."""
        mp3_url = self.audio_formats_urls.get("mp3")

        if not mp3_url:
            raise ValueError("MP3 file URL not found.")

        mp3 = MP3(
            url=mp3_url,
            audiowork_dir=self.audiowork_dir,
            audio_title=self.title,
            segments=False,
        )
        mp3.download()

    async def download(
        self, audio_format: Optional[AudioFormat] = PREFERRED_AUDIO_FORMAT
    ) -> None:  # pragma: no cover
        """Method to download the audio file. The download method is picked according
        to the available and preferred audio format.

        If the file already exists, the method will skip it. (Useful for series.)
        """
        if not self.audio_formats:
            return

        if audio_format and audio_format.value not in self.audio_formats:
            # Search for the first preferred available format from class AudioFormat
            crologger.info("The format %s is not available.", audio_format.value)
            audio_format = get_preferred_audio_format(self.audio_formats)
            if audio_format:
                crologger.info("Going to use %s instead.", audio_format.value)

        if not self.already_exists():
            if not self.series and not self.show:
                # Create a download dir for the audiowork when not part of series.
                create_dir_if_does_not_exist(self.audiowork_dir)

            match audio_format:
                case AudioFormat.DASH:
                    await self._download_dash()
                case AudioFormat.HLS:
                    await self._download_hls()
                case AudioFormat.MP3:
                    self._download_mp3()
                case None:
                    err_msg = f"The episdode {self.title} is not available."
                    crologger.error(err_msg)

            crologger.info("Done.")

        else:
            print(f"{self.title} již existuje.")
            crologger.info("%s already exists.", self.title)
