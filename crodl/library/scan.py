"""Scanning the on-disk download directory into the library."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from crodl.library.repository import SqliteLibraryRepository
from crodl.settings import AUDIO_FORMATS, DOWNLOAD_PATH
from crodl.streams.utils import episode_part_from_filename
from crodl.tools.logger import crologger


def local_uuid(path: Path) -> str:
    """
    Synthetic key for a file that has no Czech Radio UUID.

    Manually imported files are keyed by their path, so re-scanning the same
    file updates the same row instead of creating a duplicate.
    """
    return hashlib.sha256(str(path).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ScannedFile:
    """A file found on disk, shaped like `DownloadedWork` for the repository."""

    path: Path

    @property
    def uuid(self) -> str:
        return local_uuid(self.path)

    @property
    def title(self) -> str:
        """The file name without the episode prefix, e.g. "3 - Díl" -> "Díl"."""
        part = self.part
        if part is not None:
            without_prefix = self.path.stem.split("-", 1)[-1].strip()
            if without_prefix:
                return without_prefix
        return self.path.stem

    @property
    def part(self) -> Optional[int]:
        return episode_part_from_filename(self.path.name)

    @property
    def duration(self) -> Optional[int]:
        return None

    @property
    def since(self) -> str:
        return ""

    @property
    def description(self) -> Optional[str]:
        return None

    @property
    def author(self) -> Optional[str]:
        return None

    @property
    def short_title(self) -> Optional[str]:
        return None

    @property
    def audio_formats(self) -> Optional[list[str]]:
        return None

    @property
    def asset_url(self) -> Optional[str]:
        return None


class LibraryScan:
    """Syncs the audio files on disk into the library."""

    def __init__(
        self,
        repository: Optional[SqliteLibraryRepository] = None,
        download_path: Path = DOWNLOAD_PATH,
    ) -> None:
        self.repository = repository or SqliteLibraryRepository()
        self.download_path = download_path

    def audio_files(self) -> list[Path]:
        """Every downloaded audio file; chunk directories are skipped."""
        files = []
        for root, _, names in os.walk(self.download_path):
            if ".chunks" in root:
                continue
            for name in names:
                if name.lower().endswith(AUDIO_FORMATS):
                    files.append(Path(root) / name)
        return files

    async def sync_all(self) -> dict[str, int]:
        """Ensures every audio file on disk has a library row."""
        crologger.info("Starting library scan...")
        results = {"success": 0, "failed": 0}

        for path in self.audio_files():
            try:
                await self.repository.save_download(
                    ScannedFile(path),
                    path,
                    audio_format=path.suffix.lstrip("."),
                    is_manual=True,
                )
                results["success"] += 1
                crologger.info("Scanned: %s", path.name)
            except Exception as error:  # one bad file must not stop the scan
                crologger.error("Scan failed for %s: %s", path.name, error)
                results["failed"] += 1

        return results
