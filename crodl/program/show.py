import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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
from crodl.streams.utils import create_dir_if_does_not_exist, title_with_part
from crodl.tools.logger import crologger


@dataclass
class Show(Content):
    """
    Class for processing Shows by ČRo.
    Example: https://www.mujrozhlas.cz/dan-barta-nevinnosti-sveta
    """

    download_dir: Path = field(init=False)

    def __post_init__(self):
        if not self.uuid:
            self.uuid = self.client.get_show_uuid(self.url)  # type: ignore

        if not self.uuid:
            raise ValueError(f"Could not find show UUID for URL: {self.url}")

        # Fetch the JSON data from Show API
        json_data = self.client.get_show_data(self.uuid)

        attributes = Attributes(
            title=json_data["data"]["attributes"]["title"],
            active=json_data["data"]["attributes"]["active"],
            aired=json_data["data"]["attributes"]["aired"],
            description=json_data["data"]["attributes"]["description"],
            short_description=json_data["data"]["attributes"]["shortDescription"],
        )

        data = Data(
            show_type=json_data["data"]["type"],
            uuid=json_data["data"]["id"],
            attributes=attributes,
        )

        self.title = json_data["data"]["attributes"]["title"]
        self.json = json_data
        self.data = data
        episodes_data = self.client.get_related_data(
            f"{API_SERVER}/shows/{self.uuid}/episodes"
        )
        self.episodes = Episodes(
            show_title=self.title, show_id=self.uuid, json_data=episodes_data
        )
        self.download_dir = DOWNLOAD_PATH / self.title

    @property
    def downloaded_parts(self) -> int:
        crologger.info("Checking whether the show has been already downloaded...")
        if not os.path.isdir(self.download_dir):
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

    async def download(
        self, audio_format: Optional[AudioFormat] = PREFERRED_AUDIO_FORMAT
    ) -> None:
        """Downloads all episodes of the series to their own subfolders."""
        create_dir_if_does_not_exist(self.download_dir)

        for episode in self.episodes.info:
            download_to = self.download_dir
            audio_work = AudioWork(
                uuid=episode.get("uuid"),  # type: ignore
                audiowork_dir=download_to,
                title=title_with_part(episode.get("title"), episode.get("part")),  # type: ignore
                since=episode.get("since"),  # type: ignore
                show=True,
                client=self.client,
            )

            await audio_work.download(audio_format)
