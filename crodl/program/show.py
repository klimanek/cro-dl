from dataclasses import dataclass, field
import os

from typing import Optional
from pathlib import Path

from crodl.settings import (
    API_SERVER,
    DOWNLOAD_PATH,
    AudioFormat,
    PREFERRED_AUDIO_FORMAT,
    AUDIO_FORMATS,
)
from crodl.program.audiowork import AudioWork
from crodl.program.content import Content
from crodl.data.attributes import Data, Attributes, Episodes

from crodl.streams.utils import create_dir_if_does_not_exist, title_with_part
from crodl.tools.logger import crologger
from crodl.tools.scrap import (
    cro_session,
    get_show_uuid,
)


@dataclass
class Show(Content):
    """
    Class for processing Shows by ČRo.
    Example: https://www.mujrozhlas.cz/dan-barta-nevinnosti-sveta

    In HTML, we look for show uuid -- found: 1a9044a7-18a2-32fe-870a-32ec9bf33c74
    Then we use an API call to get info on this show:
        https://api.mujrozhlas.cz/shows/1a9044a7-18a2-32fe-870a-32ec9bf33c74
    Corresponding show episodes are then taken from this API call:
        https://api.mujrozhlas.cz/shows/1a9044a7-18a2-32fe-870a-32ec9bf33c74/episodes
    """

    download_dir: Path = field(init=False)

    def __post_init__(self):
        show_id = get_show_uuid(self.url, cro_session)
        show_api_url = f"{API_SERVER}/shows/{show_id}"

        # Fetch the JSON data from Show URL
        response = cro_session.get(show_api_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        json_data = response.json()

        attributes = Attributes(
            title=json_data["data"]["attributes"]["title"],
            active=json_data["data"]["attributes"]["active"],
            aired=json_data["data"]["attributes"]["aired"],
            description=json_data["data"]["attributes"]["description"],
            short_description=json_data["data"]["attributes"]["shortDescription"],
        )

        data = Data(
            type=json_data["data"]["type"],
            uuid=json_data["data"]["id"],
            attributes=attributes,
        )

        self.title = json_data["data"]["attributes"]["title"]
        self.uuid = json_data["data"]["id"]
        self.json = json_data
        self.api_url = show_api_url
        self.data = data
        self.episodes = Episodes(show_id)
        self.download_dir = DOWNLOAD_PATH / self.title

    @property
    def downloaded_parts(self) -> int:
        crologger.info("Checking whether the show has been already downloaded...")
        if not os.path.isdir(self.download_dir):
            return False

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
            )

            await audio_work.download(audio_format)
