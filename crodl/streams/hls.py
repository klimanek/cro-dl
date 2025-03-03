import os

from dataclasses import dataclass
from pathlib import Path

from yaspin import yaspin
from crodl.tools.logger import crologger

from crodl.streams.utils import get_m4a_url, process_audiowork_title
from crodl.streams.audioparts import AudioParts
from crodl.streams.download import download_parts


@dataclass
class HLS(AudioParts):
    """
    Processes a HLS stream using its chunklist, downloaded from its url. Creates
    a local chunklist.txt containing a complete list of all aac chunks which
    will be merged into one aac audio file.
    """

    @property
    def chunklist_path(self) -> Path:
        if not self.segments_path:
            raise ValueError("self.segments_path is None!")
        return self.segments_path / "chunklist.m3u8"

    def _get_chunklist_m3u8(self) -> None:
        from crodl.tools.scrap import cro_session

        mp4_url = get_m4a_url(self.url)
        chunklist_url = mp4_url + "/chunklist.m3u8"
        chunklist = cro_session.get(chunklist_url, timeout=5)
        chunklist.raise_for_status()

        crologger.info("mp4 URL: %s", mp4_url)
        crologger.info("CHUNKLIST URL: %s", chunklist_url)

        with open(self.chunklist_path, "w", encoding="utf-8") as f:
            f.write(chunklist.text)

    def _get_chunk_names(self) -> list[str]:
        with open(self.chunklist_path, encoding="utf-8") as file:
            chunks = [line.rstrip() for line in file if line.startswith("media_")]

        return chunks

    def _delete_chunklist_txt(self) -> None:
        if not self.segments_path:
            raise ValueError("self.segments_path is None!")
        crologger.info("Deleting chunklist.txt.")
        os.remove(self.segments_path / "chunklist.txt")

    def _create_list_txt(self) -> None:
        if not self.segments_path:
            raise ValueError("self.segments_path is None!")

        self._get_chunklist_m3u8()
        chunks = self._get_chunk_names()
        crologger.info("Getting file names...")

        if not chunks:
            raise ValueError("Chunklist is empty!")

        crologger.info("Renaming...")

        if not isinstance(self.segments_path, Path):
            self.segments_path = Path(self.segments_path)
        list_path = Path(self.segments_path / "list.txt")

        with list_path.open("w", encoding="utf-8") as list_txt:
            for line in chunks:
                list_txt.write(line + "\n")
        crologger.info("The list.txt file with new titles was created successfully.")

    def chunks_urls(self) -> list[str]:
        mp4_url = get_m4a_url(self.url)
        chunks = self._get_chunk_names()

        return [mp4_url + "/" + chunk for chunk in chunks]

    def _merge_chunks(self, audio_format: str) -> None:
        if not self.audiowork_dir:
            raise ValueError("self.audiowork_dir is None!")
        if not self.segments_path:
            raise ValueError("self.segments_path is None!")
        if not isinstance(self.audiowork_dir, Path):
            self.audiowork_dir = Path(self.audiowork_dir)

        title_and_extension = (
            f"{process_audiowork_title(self.audio_title)}.{audio_format}"
        )
        output_file = self.audiowork_dir / title_and_extension
        segment_files = [
            self.segments_path / f"media_{i}.{audio_format}"
            for i in range(len(self.chunks_urls()))
        ]

        crologger.info("Merging segments...")
        with open(output_file, "wb") as output:
            for segment in segment_files:
                # crologger.info("Merging segments %s: ", segment)
                with open(segment, "rb") as f:
                    output.write(f.read())

    async def download(self) -> None:
        if not self.segments_path:
            raise ValueError("self.segments_path is not set!")

        with yaspin(text=f"Zpracovávám {self.audio_title}", color="yellow") as _:
            self._create_list_txt()

        with yaspin(text=f"Stahuji {self.audio_title}", color="yellow") as _:
            await download_parts(self.chunks_urls(), self.segments_path)

        with yaspin(text=f"Ukládám {self.audio_title}", color="yellow") as spinner:
            self._merge_chunks("aac")
            self._purge_chunks_dir()
            spinner.ok("✔️")
