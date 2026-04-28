import os
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

from rich.progress import Progress

from crodl.data.attributes import Attributes, Data, Episodes
from crodl.program.audiowork import AudioWork
from crodl.program.content import Content
from crodl.settings import (
    API_SERVER,
    AUDIO_FORMATS,
    DOWNLOAD_PATH,
    PREFERRED_AUDIO_FORMAT,
    AudioFormat,
)
from crodl.streams.utils import create_dir_if_does_not_exist, title_with_part, process_audiowork_title
from crodl.tools.logger import crologger


@dataclass
class Show(Content):
    """
    Class for processing Shows by ČRo.
    Example: https://www.mujrozhlas.cz/dan-barta-nevinnosti-sveta
    """

    download_dir: Optional[Path] = field(default=None)
    remove_accents: bool = False

    def __post_init__(self):
        if not self.uuid and self.url:
            self.uuid = self.client.get_show_uuid(self.url)

        if not self.uuid:
            raise ValueError(f"Could not find show UUID for URL: {self.url}")

        # Fetch the JSON data from Show API
        json_data = self.client.get_show_data(self.uuid)

        attributes = Attributes(
            title=str(json_data["data"]["attributes"]["title"]),
            active=bool(json_data["data"]["attributes"]["active"]),
            aired=bool(json_data["data"]["attributes"]["aired"]),
            description=str(json_data["data"]["attributes"]["description"]),
            short_description=str(json_data["data"]["attributes"]["shortDescription"]),
        )

        data = Data(
            show_type=str(json_data["data"]["type"]),
            uuid=str(json_data["data"]["id"]),
            attributes=attributes,
        )

        # Use custom title if provided, otherwise fallback to API title
        if self.title == "Unknown" or not self.title:
            self.title = str(json_data["data"]["attributes"]["title"])
            
        self.json = json_data
        self.data = data
        episodes_data = self.client.get_related_data(
            f"{API_SERVER}/shows/{self.uuid}/episodes"
        )
        self.episodes = Episodes(
            show_title=self.title, show_id=self.uuid, json_data=episodes_data
        )
        
        if not self.download_dir:
            self.download_dir = DOWNLOAD_PATH / process_audiowork_title(self.title, remove_accents=self.remove_accents)

    @property
    def downloaded_parts(self) -> int:
        crologger.info("Checking whether the show has been already downloaded...")
        if not self.download_dir or not os.path.isdir(self.download_dir):
            return 0

        downloaded_parts = sum(
            1
            for file in os.listdir(self.download_dir)
            if file.lower().endswith(AUDIO_FORMATS)
        )

        crologger.info("Parts downloaded: %s", downloaded_parts)
        crologger.info("Total parts: %s", self.episodes.count)

        return downloaded_parts

    def already_exists(self) -> bool:
        return self.downloaded_parts == self.episodes.count

    async def _download_episode(
        self, episode: dict, audio_format: Optional[AudioFormat], semaphore: asyncio.Semaphore, progress: Progress
    ) -> None:
        """Helper to download a single episode with semaphore control."""
        async with semaphore:
            download_to = self.download_dir
            audio_work = AudioWork(
                uuid=episode.get("uuid"),
                audiowork_dir=download_to,
                title=title_with_part(str(episode.get("title", "Unknown")), int(episode.get("part", 0))),
                since=str(episode.get("since", "")),
                show=True,
                remove_accents=self.remove_accents,
                client=self.client,
            )
            await audio_work.download(audio_format, progress=progress)

    async def download(
        self, 
        audio_format: Optional[AudioFormat] = PREFERRED_AUDIO_FORMAT,
        progress: Optional[Progress] = None,
        task_id: Optional[Any] = None
    ) -> None:
        """Downloads all episodes of the show in parallel (limited by semaphore)."""
        if not self.download_dir:
            raise ValueError("download_dir is not set.")
            
        create_dir_if_does_not_exist(self.download_dir)

        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent downloads
        if progress:
            tasks = [
                self._download_episode(episode, audio_format, semaphore, progress)
                for episode in self.episodes.info
            ]
            await asyncio.gather(*tasks)
        else:
            with Progress() as internal_progress:
                tasks = [
                    self._download_episode(episode, audio_format, semaphore, internal_progress)
                    for episode in self.episodes.info
                ]
                await asyncio.gather(*tasks)
