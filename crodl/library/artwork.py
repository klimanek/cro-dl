"""Artwork (thumbnails/covers) for the works kept in the library."""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from crodl.tools.image_downloader import download_image
from crodl.tools.logger import crologger

# Name of the single image a multi-part work shares between its parts.
COVER_STEM = "cover"

# Image formats the downloader can store (and the scan can pick up).
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def artwork_path(url: str, audio_file: Path) -> Path:
    """Where the artwork of `audio_file` is stored (next to it, same stem)."""
    suffix = Path(urlparse(url).path).suffix or ".jpg"
    return audio_file.with_suffix(suffix)


def cover_path(url: str, directory: Path) -> Path:
    """Where the cover shared by every part of a work is stored."""
    suffix = Path(urlparse(url).path).suffix or ".jpg"
    return directory / f"{COVER_STEM}{suffix}"


def stored_artwork(audio_file: Path) -> Optional[Path]:
    """
    Artwork already lying next to a downloaded file, if there is any.

    The disk scan has no API access, so it can only reuse the images an earlier
    download (or the user) left on disk: the file's own `<stem>.jpg` first, then
    the cover shared by the whole work.
    """
    for suffix in IMAGE_SUFFIXES:
        candidate = audio_file.with_suffix(suffix)
        if candidate.exists():
            return candidate

    for suffix in IMAGE_SUFFIXES:
        candidate = audio_file.parent / f"{COVER_STEM}{suffix}"
        if candidate.exists():
            return candidate

    return None


async def fetch_artwork(url: Optional[str], audio_file: Path) -> Optional[Path]:
    """
    Downloads the work's own artwork next to its audio file.

    Returns None when the API provides no image or the download fails -
    missing artwork must never fail a download.
    """
    if not url:
        return None

    return await _download(url, artwork_path(url, audio_file), audio_file.name)


async def fetch_cover(url: str, directory: Path) -> Optional[Path]:
    """
    Downloads the image all parts of a work have in common into `directory`.

    One file per work instead of one per part: the parts of a reading, say,
    repeat the same picture, so fetching it for every episode would download
    the identical image a dozen times over.
    """
    target = cover_path(url, directory)
    return await _download(url, target, target.name)


async def _download(url: str, target: Path, label: str) -> Optional[Path]:
    saved = await download_image(url, target)

    if saved is None:
        crologger.warning("No artwork stored for %s", label)

    return saved
