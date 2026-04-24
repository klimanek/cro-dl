import os
from dataclasses import dataclass
from pathlib import Path
from rich.progress import Progress

from crodl.tools.logger import crologger
from crodl.streams.utils import get_m4a_url, process_audiowork_title, shorten_title
from crodl.streams.audioparts import AudioParts
from crodl.streams.download import download_parts

from crodl.settings import TIMEOUT


@dataclass
class HLS(AudioParts):
    """
    Processes a HLS stream using its chunklist.
    """

    @property
    def chunklist_path(self) -> Path:
        if not self.segments_path:
            raise ValueError("self.segments_path is None!")
        return self.segments_path / "chunklist.m3u8"

    def _get_chunklist_m3u8(self) -> None:
        from requests import Session

        session = self.session or Session()

        mp4_url = get_m4a_url(self.url)
        chunklist_url = mp4_url + "/chunklist.m3u8"
        chunklist = session.get(chunklist_url, timeout=TIMEOUT)
        chunklist.raise_for_status()

        crologger.info("mp4 URL: %s", mp4_url)
        crologger.info("CHUNKLIST URL: %s", chunklist_url)

        with open(self.chunklist_path, "w", encoding="utf-8") as f:
            f.write(chunklist.text)

    def _get_chunk_names(self) -> list[str]:
        with open(self.chunklist_path, encoding="utf-8") as file:
            chunks = [line.rstrip() for line in file if line.startswith("media_")]

        return chunks

    def _create_list_txt(self) -> None:
        if not self.segments_path:
            raise ValueError("self.segments_path is None!")

        self._get_chunklist_m3u8()
        chunks = self._get_chunk_names()
        crologger.info("Generating list.txt for ffmpeg...")

        if not chunks:
            raise ValueError("Chunklist is empty!")

        list_path = self.segments_path / "list.txt"
        with list_path.open("w", encoding="utf-8") as list_txt:
            for line in chunks:
                list_txt.write(line + "\n")
        crologger.info("The list.txt file was created successfully.")

    def chunks_urls(self) -> list[str]:
        mp4_url = get_m4a_url(self.url)
        chunks = self._get_chunk_names()

        return [mp4_url + "/" + chunk for chunk in chunks]

    async def download(self, progress: Progress = None, task_id=None) -> None:
        self._prepare_directories()

        if not self.segments_path:
            raise ValueError("self.segments_path is not set!")

        self._create_list_txt()
        urls = self.chunks_urls()

        if progress:
            if task_id is None:
                task_id = progress.add_task(
                    shorten_title(self.audio_title, 20), total=len(urls)
                )
            await download_parts(urls, self.segments_path, progress_callback=lambda: progress.update(task_id, advance=1))
        else:
            with Progress() as internal_progress:
                task_id = internal_progress.add_task(
                    shorten_title(self.audio_title, 20), total=len(urls)
                )
                await download_parts(urls, self.segments_path, progress_callback=lambda: internal_progress.update(task_id, advance=1))

        # Merge using ffmpeg via base class method
        self._merge_chunks("aac")
        self._purge_chunks_dir()
        crologger.info("HLS download completed.")
