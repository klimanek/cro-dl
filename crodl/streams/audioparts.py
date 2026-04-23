from abc import ABC, abstractmethod
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
import shutil

from typing import Optional
from requests import Session

from crodl.settings import DOWNLOAD_PATH, SEGMENTS_SUBDIR, SUPPORTED_AUDIO_FORMATS
from crodl.tools.logger import crologger
from crodl.streams.utils import create_dir_if_does_not_exist, process_audiowork_title


@dataclass
class AudioParts(ABC):
    """
    Abstract base class for all audio downloaders.
    Handles common tasks like directory management and merging segments.
    """

    url: str
    audio_title: str
    audiowork_dir: Path | None = field(default=None)
    segments_path: Path | None = field(default=None)
    segments: bool = True
    session: Optional[Session] = field(default=None, repr=False)

    def __post_init__(self):
        """Basic validation and logging."""
        crologger.info(f"Initializing downloader for: {self.audio_title}")

        if self.audiowork_dir and not isinstance(self.audiowork_dir, Path):
            self.audiowork_dir = Path(self.audiowork_dir)

    def _prepare_directories(self) -> None:
        """Creates necessary directories for downloading and processing."""
        if not self.audiowork_dir:
            self.audiowork_dir = DOWNLOAD_PATH / process_audiowork_title(
                self.audio_title
            )
            crologger.info("Set audiowork_dir to %s", self.audiowork_dir)

        create_dir_if_does_not_exist(self.audiowork_dir)

        if self.segments:
            if not self.segments_path:
                self.segments_path = self.audiowork_dir / SEGMENTS_SUBDIR

            create_dir_if_does_not_exist(self.segments_path)

    @abstractmethod
    async def download(self) -> None:
        """Abstract method to be implemented by subclasses."""
        pass

    def _merge_chunks(self, audio_format: str) -> None:
        """
        Merges chunks of audio files into a final audiowork using ffmpeg.
        Expects a list.txt file in the segments directory.
        """
        if audio_format not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(f"Format '{audio_format}' is not supported!")

        if not self.segments_path:
            raise ValueError("segments_path is not set")

        crologger.info("Merging files using ffmpeg...")
        output_filename = f"{process_audiowork_title(self.audio_title)}.{audio_format}"
        # The output path should be in the parent of segments_path (which is audiowork_dir)
        output_path = self.audiowork_dir / output_filename if self.audiowork_dir else Path(f"../{output_filename}")

        command = [
            "ffmpeg",
            "-i",
            "concatf:list.txt",
            "-c",
            "copy",
            str(output_path),
            "-loglevel",
            "quiet",
            "-y",  # Overwrite output files without asking
        ]

        subprocess.run(command, cwd=str(self.segments_path), check=True)
        crologger.info("Merging completed: %s", output_path)

    def _purge_chunks_dir(self) -> None:
        """Deletes temporary directory with audio chunks."""
        if not self.segments_path:
            return

        if self.segments_path.exists():
            crologger.info("Deleting temporary segments directory: %s", self.segments_path)
            shutil.rmtree(self.segments_path)
