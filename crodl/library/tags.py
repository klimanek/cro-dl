"""Writing what the library knows about a work into its audio files."""

import asyncio
from pathlib import Path
from typing import Optional

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp4 import MP4

from crodl.tools.logger import crologger

#: Formats cro-dl can tag (the extensions its downloaders produce).
TAGGABLE = (".mp3", ".m4a", ".aac", ".mp4")

#: MP4 ("M4A"/"AAC") names its tags differently from ID3.
MP4_KEYS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "genre": "\xa9gen",
}

#: Extensions that hold ID3 tags, including raw AAC: Czech Radio streams come
#: down as ADTS `.aac`, which has no container to put tags in - an ID3 chunk in
#: front of it is what players (VLC, foobar2000, ...) expect and read.
ID3_SUFFIXES = (".mp3", ".aac")


async def read_tags(path: Path) -> dict[str, str]:
    """The tags a player would show for `path` (empty when there are none)."""
    return await asyncio.to_thread(read_tags_now, path)


def read_tags_now(path: Path) -> dict[str, str]:
    """Reads the tags off the file, so edit mode can offer them for correction."""
    if path.suffix.lower() not in TAGGABLE or not path.exists():
        return {}

    try:
        if path.suffix.lower() in ID3_SUFFIXES:
            raw: dict[str, object] = dict(EasyID3(str(path)))
        else:
            audio = MP4(str(path))
            raw = {}

            for key, mp4_key in MP4_KEYS.items():
                values = audio.get(mp4_key)
                if values:
                    raw[key] = values[0]

            track = audio.get("trkn")
            if track:
                raw["tracknumber"] = str(track[0][0])
    except Exception as error:  # a file without tags is not an error
        crologger.warning("Could not read tags of %s: %s", path.name, error)
        return {}

    return {
        key: value[0] if isinstance(value, list) else str(value)
        for key, value in raw.items()
        if value
    }


def wanted(
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[int] = None,
) -> dict[str, str]:
    """The tags to write, without the ones nobody knows."""
    fields = {
        "title": title,
        "artist": author,
        "album": album,
        "genre": genre,
        "tracknumber": str(track) if track else None,
    }

    return {key: str(value) for key, value in fields.items() if value}


async def write_tags(
    path: Path,
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[int] = None,
) -> bool:
    """
    Writes the tags a player reads into `path`; False when it cannot.

    Tagging runs in a thread (it is file I/O on a file that may be large) and a
    file that cannot be tagged only logs a warning: a download that landed is a
    download, tags or no tags.
    """
    return await asyncio.to_thread(
        write_tags_now,
        path,
        title=title,
        author=author,
        album=album,
        genre=genre,
        track=track,
    )


def write_tags_now(
    path: Path,
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[int] = None,
) -> bool:
    """The tagging itself, on the calling thread."""
    tags = wanted(title=title, author=author, album=album, genre=genre, track=track)

    if not tags or path.suffix.lower() not in TAGGABLE or not path.exists():
        return False

    try:
        if path.suffix.lower() in ID3_SUFFIXES:
            _write_mp3(path, tags)
        else:
            _write_mp4(path, tags)
    except Exception as error:  # never fail a download over a tag
        crologger.warning("Could not tag %s: %s", path.name, error)
        return False

    crologger.info("Tagged %s (%s)", path.name, ", ".join(sorted(tags)))
    return True


def _write_mp3(path: Path, tags: dict[str, str]) -> None:
    """ID3 tags; a file without any gets its first tag chunk."""
    try:
        existing = EasyID3(str(path))
    except ID3NoHeaderError:
        existing = EasyID3()

    for key, value in tags.items():
        existing[key] = value

    existing.save(str(path))


def _write_mp4(path: Path, tags: dict[str, str]) -> None:
    """MP4 tags (MP4 files cannot be created from scratch, so this needs one)."""
    audio = MP4(str(path))

    for key, value in tags.items():
        if key == "tracknumber":
            audio["trkn"] = [(int(value), 0)]
        elif key in MP4_KEYS:
            audio[MP4_KEYS[key]] = [value]

    audio.save()
