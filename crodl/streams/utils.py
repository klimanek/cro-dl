import datetime
import os
import re
import itertools

from pathlib import Path
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from crodl.settings import AudioFormat, DOWNLOAD_PATH
from crodl.tools.logger import crologger

if TYPE_CHECKING:
    from crodl.program.audiowork import AudioWork


def get_m4a_url(audio_link: str) -> str:
    """Returns the URL of a m4a dir with chunks (m4s or acc)

    Args:
        audio_link (str) -- URL of the audiowork (represented by 'manifest.mpd' or 'playlist.m3u8')

    Returns:
        Optional (str) -- URL of the m4a dir or None if neither pattern is found.

    """
    if "manifest.mpd" in audio_link:
        return audio_link.replace("/manifest.mpd", "")
    if "playlist.m3u8" in audio_link:
        return audio_link.replace("/playlist.m3u8", "")

    raise ValueError("Audio link is not valid.")


def partial_sums(nlist: list[int]) -> list[int]:
    """Returns a partial sums list of input list elements.

    Example:
        numbers = [6, 5, 6, 5, 6, 3],
        result = [6, 11, 17, 22, 28, 31]
    """
    return list(itertools.accumulate(nlist))


def get_preferred_audio_format(audio_variants: list[str]) -> AudioFormat | None:
    """
    Get the preferred audio format from a list of audio variants.

    Args:
        audio_variants (list[str]): A list of audio variants to choose from.

    Returns:
        AudioFormat: The preferred audio format, or None if none of the variants
        match the available formats.
    """
    for audio_format in AudioFormat:
        if audio_format.value in audio_variants:
            return audio_format

    return None


def process_audiowork_title(title: str, prefix: str | None = None) -> str:
    """Process the audiowork title to get a valid filename.
    Getting rid of a colon and a slash, replacing them with a dash."""
    if ":" in title:
        title = title.replace(":", " -")

    if "/" in title:
        title = title.replace("/", "-")

    if prefix:
        title = f"{prefix} - {title}"
    return title[:250]


def audio_segment_sort(filename) -> int | float:
    # Extract the numeric part from the filename
    # Making sure the format / suffix is not used
    filename = filename.split(".")[0]
    match = re.search(r"\d+", filename)
    if match:
        return int(match.group())
    return float("inf")  # Return infinity for non-numeric filenames


def simplify_audio_name(manifest_id: str, audio_name: str) -> str:
    """Renames complicated names by CRo.

    Example:
        segment_ctaudio_ridp0aa0br193031_cs80640000_mpd.m4s
        -> 80640000.m4s

        where the new name is basically a time stamp of DASH stream segment.

        "segment_ctaudio_rid" is a prefix,
        "p0aa0br193031" is a manifest_id

    """

    prefix = "segment_ctaudio_rid"

    # Removing characters from the left
    if "cinit" not in audio_name:
        audio_name = audio_name.replace(prefix + manifest_id + "_cs", "")
    else:
        audio_name = audio_name.replace(prefix + manifest_id + "_", "")

    # Removing characters from the right
    audio_name = audio_name.replace("_mpd", "").strip()

    return audio_name


def create_dir_if_does_not_exist(path: Path) -> None:
    if not path:
        raise ValueError("Path cannot be empty.")
    if not Path(path).exists():
        crologger.info("Creating a dir %s", path)
        os.makedirs(path)


def day_month_year(json_time: str) -> str:
    date_obj = datetime.datetime.strptime(json_time, "%Y-%m-%dT%H:%M:%S%z")
    return date_obj.strftime("%d-%m-%Y")


def title_with_part(title: str, part: int | str | None = None) -> str:
    if not title:
        raise ValueError("Title cannot be empty.")

    if part:
        if isinstance(part, int):
            part = str(part)
        if part.isnumeric():
            return f"{part}-{title}"
        raise ValueError("Part must be numeric.")

    return title


class HMS:
    def __init__(self, secs: int):
        self.secs = secs

    def __str__(self) -> str:
        hrs, mins, secs = self.hms()
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def hms(self) -> tuple[int, int, int]:
        """Transform seconds into hours, minutes and seconds."""
        hrs = self.secs // 3600
        mins = (self.secs % 3600) // 60
        secs = self.secs % 60
        return hrs, mins, secs


def file_size(size_in_bytes: int):
    if not isinstance(size_in_bytes, int):
        return size_in_bytes
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    if size_in_bytes < 1024**2:
        return f"{size_in_bytes / 1024:.2f} KB"

    return f"{size_in_bytes / 1024**2:.2f} MB"


def parse_date_from_json(json_time: str) -> tuple[str, str] | None:
    try:
        dt = datetime.datetime.fromisoformat(json_time)
    except ValueError:
        print("Cannot process the date.")
        dt = None
    return (dt.strftime("%d.%m.%Y"), dt.strftime("%H:%M")) if dt else None


def create_a_file_if_does_not_exist(path: Path, msg: Optional[str] = "") -> None:
    """Creates an empty file if it does not exist"""
    if not os.path.exists(path):
        crologger.info("Creatiung %s", path)

        try:
            with open(path, "w", encoding="utf-8") as f:
                if msg:
                    f.write(msg)
        except IOError as err:
            crologger.error(err)
            raise err


def not_available_yet(audiowork: "AudioWork") -> str:
    msg = "Datum a čas dostupnosti díla nebyl nalezen."
    err_msg = "Cannot find the release date and time. Data missing."

    if not audiowork.since:
        crologger.error(err_msg)
        return msg

    parsed_since = parse_date_from_json(audiowork.since)

    if not parsed_since:
        crologger.error(err_msg)
        return msg

    since = datetime.datetime.fromisoformat(audiowork.since)
    now = datetime.datetime.now(ZoneInfo("Europe/Prague"))

    if now < since:
        msg = f"Epizoda bude uvedena {parsed_since[0]} v {parsed_since[1]}."
        # create_a_file_if_not_exists(audiowork.audiowork_root + "/.series")
    else:
        crologger.info(
            f"Aired: {parsed_since[0]} at {parsed_since[1]}. Copryright license might have expired."
        )
        msg = f"Epizoda byla uvedena {parsed_since[0]} v {parsed_since[1]}. Možná vypršela práva."

    return msg


def unfinished_series() -> list[str]:
    series = []
    for root, _, files in os.walk(DOWNLOAD_PATH):
        if ".series" in files:
            series.append(root)
    return series


def shorten_title(title: str, length_limit: int) -> str:
    """Shortens the title if it is too long for console."""
    if len(title) > length_limit:
        return title[: length_limit - 3] + "..."
    return title


def get_audioformat_enum_by_value(val: str) -> AudioFormat | None:
    """Searches the enum AudioFormat by its value.

    Args:
        val (str): AudioFormat value (e.g. 'dash')

    Returns:
        AudioFormat: The AudioFormat enum (e.g. 'AudioFormat.DASH')
    """
    for key in AudioFormat:
        if key.value == val:
            return key
    return None


def remove_html_tags(text: str | None) -> str | None:
    """Removes HTML tags from text."""
    html_pattern = re.compile("<.*?>")
    if text:
        clean_text = re.sub(html_pattern, "", text)
        clean_text = clean_text.replace("&nbsp;", " ")
        return clean_text
    return None
