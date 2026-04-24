from pathlib import Path
from enum import Enum

HOME_DIR = Path.home()
DOWNLOAD_DIR = "Z Rozhlasu"
SEGMENTS_SUBDIR = ".chunks"
DOWNLOAD_PATH = HOME_DIR / DOWNLOAD_DIR
SERIES_DOWNLOAD_DIR = "Seriály"
LOG_PATH = DOWNLOAD_PATH / "logs"
DB_PATH = DOWNLOAD_PATH / "library.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
SUPPORTED_DOMAINS = ("www.mujrozhlas.cz", "mujrozhlas.cz")
SUPPORTED_AUDIO_FORMATS = ("aac", "m4a")
AUDIO_FORMATS = SUPPORTED_AUDIO_FORMATS + ("mp3",)


class AudioFormat(Enum):
    """The order determines the order of the audio downloads, if available."""

    MP3 = "mp3"
    HLS = "hls"
    DASH = "dash"


PREFERRED_AUDIO_FORMAT = AudioFormat.MP3

API_SERVER = "https://api.mujrozhlas.cz/"
TIMEOUT = 10
