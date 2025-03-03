import subprocess
from pathlib import Path
from dataclasses import dataclass, field
import shutil

from yaspin import yaspin

from crodl.settings import DOWNLOAD_PATH, SEGMENTS_SUBDIR, SUPPORTED_AUDIO_FORMATS
from crodl.tools.logger import crologger
from crodl.streams.utils import create_dir_if_does_not_exist, process_audiowork_title


@dataclass
class AudioParts:
    url: str
    audio_title: str
    audiowork_dir: Path | None = field(default=None)
    segments_path: Path | None = field(default=None)
    segments: bool = True

    def __post_init__(self):
        """After class init, this method will create audiowork_dir if it doesn't exist."""
        crologger.info(self.audio_title)

        if not self.audiowork_dir:
            self.audiowork_dir = DOWNLOAD_PATH / process_audiowork_title(
                self.audio_title
            )
            crologger.info("Creating an attribute %s", self.audiowork_dir)

        if not isinstance(self.audiowork_dir, Path):
            self.audiowork_dir = Path(self.audiowork_dir)

        if self.segments:
            if not self.segments_path:
                self.segments_path = Path(self.audiowork_dir) / SEGMENTS_SUBDIR

            create_dir_if_does_not_exist(self.segments_path)

    def _merge_chunks(self, audio_format: str) -> None:
        """
        Merges chunks of audio files into a final audiowork using ffmpeg.
        """
        if audio_format not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(f"Format '{audio_format}' is not supported!")

        subdirectory = f"{self.segments_path}"
        crologger.info("Merging files...")
        command = [
            "ffmpeg",
            "-i",
            "concatf:list.txt",
            "-c",
            "copy",
            f"../{process_audiowork_title(self.audio_title)}.{audio_format}",
            "-loglevel",
            "quiet",
        ]

        with yaspin(text=f"Ukládám {self.audio_title}", color="yellow") as spinner:
            subprocess.run(command, cwd=subdirectory, check=True)
            spinner.ok("✔️")

    def _purge_chunks_dir(self) -> None:  # pragma: no cover
        """Deletes tmp directory with audio chunks."""
        if not self.segments_path:
            raise ValueError("segments_path was not set")

        if Path.exists(self.segments_path):
            crologger.info("Deleting .chunks...")
            shutil.rmtree(self.segments_path)
