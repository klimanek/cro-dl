from dataclasses import dataclass


import requests
from rich.progress import Progress

from crodl.streams.audioparts import AudioParts
from crodl.streams.utils import process_audiowork_title, shorten_title
from crodl.tools.logger import crologger


@dataclass
class MP3(AudioParts):
    """Process mp3 stream from CRo"""

    def download(self) -> None:
        """Download audiowork mp3 file"""
        file_url = self.url
        crologger.info("Downloading mp3: %s", file_url)

        with requests.get(file_url, timeout=4, stream=True) as resp:
            content_length = resp.headers.get("Content-Length")

            if not self.audiowork_dir:
                raise ValueError("self.audiowork_dir is not set.")

            if not content_length:
                raise ValueError("The file cannot be downloaded.")

            total_length = int(content_length)

            with Progress() as progress:
                task = progress.add_task(
                    shorten_title(self.audio_title, 20), total=total_length
                )

                audio_full_path = (
                    self.audiowork_dir
                    / f"{process_audiowork_title(self.audio_title)}.mp3"
                )
                with audio_full_path.open("wb") as output:
                    while True:
                        chunk = resp.raw.read(1024)
                        if not chunk:
                            break

                        output.write(chunk)
                        progress.update(task, advance=len(chunk))
