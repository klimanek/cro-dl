"""Artwork (thumbnails/covers) for the works kept in the library."""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from crodl.tools.image_downloader import download_image
from crodl.tools.logger import crologger


def artwork_path(url: str, audio_file: Path) -> Path:
    """Where the artwork of `audio_file` is stored (next to it, same stem)."""
    suffix = Path(urlparse(url).path).suffix or ".jpg"
    return audio_file.with_suffix(suffix)


async def fetch_artwork(url: Optional[str], audio_file: Path) -> Optional[Path]:
    """
    Downloads the work's artwork next to its audio file.

    Returns None when the API provides no image or the download fails -
    missing artwork must never fail a download.
    """
    if not url:
        return None

    target = artwork_path(url, audio_file)
    saved = await download_image(url, target)

    if saved is None:
        crologger.warning("No artwork stored for %s", audio_file.name)

    return saved
