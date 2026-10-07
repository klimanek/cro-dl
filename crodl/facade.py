from typing import Optional, Union, TYPE_CHECKING
from pathlib import Path
from urllib.parse import urlparse
from rich.progress import Progress

from crodl.program.audiowork import AudioWork
from crodl.program.series import Series
from crodl.program.show import Show
from crodl.tools.api_client import CroAPIClient
from crodl.settings import SUPPORTED_DOMAINS, AudioFormat, PREFERRED_AUDIO_FORMAT
from crodl.tools.logger import crologger

if TYPE_CHECKING:
    from crodl.library.repository import DownloadStore


class CroDL:
    """
    Facade for the cro-dl library.
    Provides a simplified interface for resolving URLs and downloading content.
    """

    def __init__(
        self,
        client: Optional[CroAPIClient] = None,
        library: Optional["DownloadStore"] = None,
    ):
        self.client = client or CroAPIClient()
        self.library = library

    def is_domain_supported(self, url: str) -> bool:
        """Checks whether the website with 'hidden' audio lies in a supported domain."""
        try:
            domain = urlparse(url).netloc
            if not domain:
                return False
            # Support both with and without 'www.'
            clean_domain = domain.replace("www.", "")
            supported_clean = [d.replace("www.", "") for d in SUPPORTED_DOMAINS]
            return clean_domain in supported_clean
        except Exception:
            return False

    async def get_content(
        self,
        url: str,
        title: Optional[str] = None,
        output_dir: Optional[Path] = None,
        remove_accents: bool = False,
    ) -> Union[AudioWork, Series, Show]:
        """
        Resolves a URL to a specific content type (AudioWork, Series, or Show).
        Applies custom title, output directory and accent removal settings.
        """
        if not self.is_domain_supported(url):
            raise ValueError(f"Unsupported domain: {urlparse(url).netloc}")

        crologger.info("Resolving content for URL: %s", url)

        # The order of checks matters
        if self.client.is_show(url):
            crologger.info("URL resolved as Show")
            content: Union[AudioWork, Series, Show] = Show(
                url=url,
                title=title or "Unknown",
                download_dir=output_dir,
                remove_accents=remove_accents,
                client=self.client,
            )
        elif self.client.is_series(url):
            crologger.info("URL resolved as Series")
            content = Series(
                url=url,
                title=title or "Unknown",
                download_dir=output_dir,
                remove_accents=remove_accents,
                client=self.client,
            )
        else:
            crologger.info("URL resolved as AudioWork (Episode/Broadcast)")
            content = AudioWork(
                url=url,
                title=title or "Unknown",
                audiowork_dir=output_dir,
                remove_accents=remove_accents,
                client=self.client,
            )

        # Constructors are I/O free, so the API data is loaded here - exactly once.
        await content.load()

        return content

    async def download(
        self,
        content: Union[AudioWork, Series, Show],
        audio_format: AudioFormat = PREFERRED_AUDIO_FORMAT,
        progress: Optional[Progress] = None,
    ) -> None:
        """
        Starts the download process for the given content.

        Finished works are handed to the configured library (if any) through
        the `on_downloaded` hook - the core knows nothing about storage.
        """
        crologger.info(
            "Starting download for: %s (Format: %s)", content.title, audio_format.value
        )
        await content.download(
            audio_format=audio_format,
            progress=progress,
            on_downloaded=self._record_download,
        )

    async def _record_download(self, work: AudioWork, path: Path) -> None:
        """Hook that stores a finished download in the local library."""
        if self.library is None:
            return

        await self.library.save_download(
            work, path, audio_format=path.suffix.lstrip(".")
        )
