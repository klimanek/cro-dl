import datetime
import os
import re
import itertools
import unicodedata

from pathlib import Path
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from crodl.settings import AudioFormat, DOWNLOAD_PATH
from crodl.tools.logger import crologger

if TYPE_CHECKING:
    from crodl.program.audiowork import AudioWork


def get_m4a_url(audio_link: str) -> str:
    """Returns the URL of a m4a dir with chunks (m4s or acc)"""
    if "manifest.mpd" in audio_link:
        return audio_link.replace("/manifest.mpd", "")
    if "playlist.m3u8" in audio_link:
        return audio_link.replace("/playlist.m3u8", "")
    raise ValueError("Audio link is not valid.")


def partial_sums(nlist: list[int]) -> list[int]:
    """Returns a partial sums list of input list elements."""
    return list(itertools.accumulate(nlist))


def get_preferred_audio_format(audio_variants: list[str]) -> AudioFormat | None:
    """Get the preferred audio format from a list of audio variants."""
    for audio_format in AudioFormat:
        if audio_format.value in audio_variants:
            return audio_format
    return None


def sanitize_filename(name: str, remove_accents: bool = False) -> str:
    """
    Sanitizes a string to be a valid filename across different OS (especially Windows).
    Removes invalid characters: <>:"/\|?*
    Also strips trailing dots and spaces which are invalid on Windows.
    """
    # 1. Replace common separators with something safe
    name = name.replace(":", " -").replace("/", "-").replace("\\", "-")
    
    # 2. Remove other invalid Windows characters
    name = re.sub(r'[<>|"*?]', '', name)
    
    # 3. Handle accents if requested
    if remove_accents:
        nfkd_form = unicodedata.normalize('NFKD', name)
        name = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        # After removing accents, we might want to ensure only basic ASCII stays
        name = name.encode('ascii', 'ignore').decode('ascii')

    # 4. Clean up whitespace and dots
    name = " ".join(name.split()) # Normalize internal spaces
    name = name.strip(". ") # Remove trailing/leading dots and spaces
    
    # 5. Limit length (Windows has 255 char limit for filename, but paths can be longer)
    return name[:200]


def process_audiowork_title(title: str, prefix: str | None = None, remove_accents: bool = False) -> str:
    """Process the audiowork title to get a valid filename."""
    sanitized = sanitize_filename(title, remove_accents=remove_accents)
    
    if prefix:
        sanitized = f"{prefix} - {sanitized}"
        
    return sanitized


def audio_segment_sort(filename) -> int | float:
    filename = filename.split(".")[0]
    match = re.search(r"\d+", filename)
    if match:
        return int(match.group())
    return float("inf")


def simplify_audio_name(manifest_id: str, audio_name: str) -> str:
    prefix = "segment_ctaudio_rid"
    if "cinit" not in audio_name:
        audio_name = audio_name.replace(prefix + manifest_id + "_cs", "")
    else:
        audio_name = audio_name.replace(prefix + manifest_id + "_", "")
    audio_name = audio_name.replace("_mpd", "").strip()
    return audio_name


def create_dir_if_does_not_exist(path: Path) -> None:
    if not path:
        raise ValueError("Path cannot be empty.")
    if not Path(path).exists():
        crologger.info("Creating a dir %s", path)
        os.makedirs(path, exist_ok=True)


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
        dt = None
    return (dt.strftime("%d.%m.%Y"), dt.strftime("%H:%M")) if dt else None


def create_a_file_if_does_not_exist(path: Path, msg: Optional[str] = "") -> None:
    if not os.path.exists(path):
        crologger.info("Creating %s", path)
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
    else:
        crologger.info(f"Aired: {parsed_since[0]} at {parsed_since[1]}. Copyright expired.")
        msg = f"Epizoda byla uvedena {parsed_since[0]} v {parsed_since[1]}. Možná vypršela práva."
    return msg


def unfinished_series() -> list[str]:
    series = []
    for root, _, files in os.walk(DOWNLOAD_PATH):
        if ".series" in files:
            series.append(root)
    return series


def shorten_title(title: str, length_limit: int) -> str:
    if len(title) > length_limit:
        return title[: length_limit - 3] + "..."
    return title


def get_audioformat_enum_by_value(val: str) -> AudioFormat | None:
    for key in AudioFormat:
        if key.value == val:
            return key
    return None


def remove_html_tags(text: str | None) -> str | None:
    html_pattern = re.compile("<.*?>")
    if text:
        clean_text = re.sub(html_pattern, "", text)
        clean_text = clean_text.replace("&nbsp;", " ")
        return clean_text
    return None


def slugify(value: str) -> str:
    """Converts a string to a URL slug."""
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)
