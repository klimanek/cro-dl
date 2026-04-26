from typing import Optional, Union
from urllib.parse import urlparse
from rich.progress import Progress

from crodl.program.audiowork import AudioWork
from crodl.program.series import Series
from crodl.program.show import Show
from crodl.tools.api_client import CroAPIClient
from crodl.settings import SUPPORTED_DOMAINS, AudioFormat, PREFERRED_AUDIO_FORMAT
from crodl.tools.logger import crologger


class CroDL:
    """
    Facade for the cro-dl library.
    Provides a simplified interface for resolving URLs and downloading content.
    """

    def __init__(self, client: Optional[CroAPIClient] = None):
        self.client = client or CroAPIClient()

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

    async def get_content(self, url: str) -> Union[AudioWork, Series, Show]:
        """
        Resolves a URL to a specific content type (AudioWork, Series, or Show).
        """
        if not self.is_domain_supported(url):
            raise ValueError(f"Unsupported domain: {urlparse(url).netloc}")

        crologger.info("Resolving content for URL: %s", url)

        # The order of checks matters
        if self.client.is_show(url):
            crologger.info("URL resolved as Show")
            return Show(url=url, client=self.client)
        
        if self.client.is_series(url):
            crologger.info("URL resolved as Series")
            return Series(url=url, client=self.client)
        
        crologger.info("URL resolved as AudioWork (Episode/Broadcast)")
        return AudioWork(url=url, client=self.client)

    async def download(self, content: Union[AudioWork, Series, Show], 
                       audio_format: AudioFormat = PREFERRED_AUDIO_FORMAT,
                       progress: Optional[Progress] = None) -> None:
        """
        Starts the download process for the given content.
        """
        crologger.info("Starting download for: %s (Format: %s)", content.title, audio_format.value)
        await content.download(audio_format=audio_format, progress=progress)
