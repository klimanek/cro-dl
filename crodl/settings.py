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

# The local web library: personal use, so it listens on the loopback interface
# only and neither the CORS policy nor the URLs ever leave the machine.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# How often a running server looks for parts the Czech Radio has released since
# (see `crodl.library.updates`); 0 switches the watch off.
UPDATE_CHECK_HOURS = 6


class AudioFormat(Enum):
    """The order determines the order of the audio downloads, if available."""

    MP3 = "mp3"
    HLS = "hls"
    DASH = "dash"


PREFERRED_AUDIO_FORMAT = AudioFormat.MP3

API_SERVER = "https://api.mujrozhlas.cz/"
TIMEOUT = 10
