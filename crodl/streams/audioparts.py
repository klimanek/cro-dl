from abc import ABC, abstractmethod
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
import shutil

from typing import Optional, Any
from requests import Session
from rich.progress import Progress

from crodl.exceptions import DownloadError
from crodl.settings import DOWNLOAD_PATH, SEGMENTS_SUBDIR, SUPPORTED_AUDIO_FORMATS
from crodl.tools.logger import crologger
from crodl.streams.utils import create_dir_if_does_not_exist, process_audiowork_title

# The `concatf:` ffmpeg protocol holds every input segment open at once
# (it must be able to seek across all of them), so merging long episodes
# needs one file descriptor per segment. A generous ceiling covers even
# multi-hour recordings while staying well within typical hard limits.
OPEN_FILE_LIMIT = 8192


def _raise_open_file_limit(minimum: int = OPEN_FILE_LIMIT) -> None:
    """
    Raise the soft limit of open files, if possible.

    Without this, ffmpeg fails with "Too many open files" (exit code 232)
    when an episode has more segments than the default soft limit
    (e.g. 256 on macOS).
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows has no `resource` module
        return

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = minimum if hard == resource.RLIM_INFINITY else min(minimum, hard)
        if target > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            crologger.info("Raised the open-file limit from %s to %s", soft, target)
    except (OSError, ValueError):  # pragma: no cover
        crologger.warning("Could not raise the open-file limit.", exc_info=True)


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
    remove_accents: bool = False
    extension: str = ""

    @property
    def output_path(self) -> Path:
        """The single file this downloader produces."""
        if not self.audiowork_dir:
            raise ValueError("audiowork_dir is not set.")

        name = process_audiowork_title(
            self.audio_title, remove_accents=self.remove_accents
        )
        return self.audiowork_dir / f"{name}.{self.extension}"

    def __post_init__(self):
        """Basic validation and logging."""
        crologger.info(f"Initializing downloader for: {self.audio_title}")

        if self.audiowork_dir and not isinstance(self.audiowork_dir, Path):
            self.audiowork_dir = Path(self.audiowork_dir)

    def _prepare_directories(self) -> None:
        """Creates necessary directories for downloading and processing."""
        if not self.audiowork_dir:
            self.audiowork_dir = DOWNLOAD_PATH / process_audiowork_title(
                self.audio_title, remove_accents=self.remove_accents
            )
            crologger.info("Set audiowork_dir to %s", self.audiowork_dir)

        create_dir_if_does_not_exist(self.audiowork_dir)

        if self.segments:
            if not self.segments_path:
                # Make segments directory unique to avoid collisions during parallel downloads
                unique_suffix = process_audiowork_title(
                    self.audio_title, remove_accents=self.remove_accents
                )
                self.segments_path = (
                    self.audiowork_dir / f"{SEGMENTS_SUBDIR}-{unique_suffix}"
                )

            create_dir_if_does_not_exist(self.segments_path)

    @abstractmethod
    async def download(
        self, progress: Optional[Progress] = None, task_id: Optional[Any] = None
    ) -> None:
        """
        Abstract method to be implemented by subclasses.
        Accepts optional rich.progress.Progress and TaskID for parallel reporting.
        """
        pass

    def _merge_chunks(self) -> None:
        """
        Merges chunks of audio files into the final audiowork using ffmpeg.
        Expects a list.txt file in the segments directory.
        """
        if self.extension not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(f"Format '{self.extension}' is not supported!")

        if not self.segments_path:
            raise ValueError("segments_path is not set")

        crologger.info("Merging files using ffmpeg...")
        # CRITICAL FIX: Always use ABSOLUTE path for output when calling subprocess
        output_path = self.output_path.absolute()

        # `concatf:` keeps all segments open at once -> raise the open-file
        # limit first, otherwise long episodes fail with "Too many open files".
        _raise_open_file_limit()

        command = [
            "ffmpeg",
            "-i",
            "concatf:list.txt",
            "-c",
            "copy",
            str(output_path),
            "-loglevel",
            "error",
            "-y",  # Overwrite output files without asking
        ]

        try:
            subprocess.run(
                command,
                cwd=str(self.segments_path),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = "\n".join((exc.stderr or "").strip().splitlines()[-5:])
            message = f"FFmpeg merge failed (exit code {exc.returncode})."
            if detail:
                message += f" {detail}"
            raise DownloadError(message) from exc
        crologger.info("Merging completed: %s", output_path)

    def _purge_chunks_dir(self) -> None:
        """Deletes temporary directory with audio chunks."""
        if not self.segments_path:
            return

        if self.segments_path.exists():
            crologger.info(
                "Deleting temporary segments directory: %s", self.segments_path
            )
            shutil.rmtree(self.segments_path)
