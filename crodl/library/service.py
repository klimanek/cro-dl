"""Library service: connects the core's download hook to storage and artwork."""

from pathlib import Path
from typing import Optional

from crodl.library.artwork import fetch_artwork
from crodl.library.models import Episode
from crodl.library.repository import DownloadedWork, SqliteLibraryRepository


class LibraryService:
    """
    Thin orchestration over `SqliteLibraryRepository`.

    This is what the facade hands to the core's `on_downloaded` hook: the core
    reports a finished file, the service fetches its artwork and stores both.
    """

    def __init__(self, repository: Optional[SqliteLibraryRepository] = None) -> None:
        self.repository = repository or SqliteLibraryRepository()

    async def save_download(
        self, work: DownloadedWork, path: Path, audio_format: Optional[str] = None
    ) -> Optional[Episode]:
        """Stores a finished download together with its artwork."""
        image_path = await fetch_artwork(work.asset_url, path)

        return await self.repository.save_download(
            work, path, audio_format=audio_format, image_path=image_path
        )
