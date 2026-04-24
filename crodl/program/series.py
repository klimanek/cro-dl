import os
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.progress import Progress

from crodl.program.audiowork import AudioWork
from crodl.program.content import Content
from crodl.settings import (
    DOWNLOAD_PATH,
    PREFERRED_AUDIO_FORMAT,
    SERIES_DOWNLOAD_DIR,
    AudioFormat,
)
from crodl.streams.utils import (
    create_a_file_if_does_not_exist,
    create_dir_if_does_not_exist,
    process_audiowork_title,
    remove_html_tags,
)
from crodl.tools.logger import crologger
from crodl.tools.scrap import get_audio_link_of_preferred_format


@dataclass
class Series(Content):
    download_dir: Optional[Path] = field(default=None)

    def __post_init__(self):
        """
        A method that is called after the class is initialized.
        """
        if not self.uuid:
            self.uuid = self.client.get_series_id(self.url)  # type: ignore

        if not self.uuid:
            crologger.error("Could not find series UUID for URL: %s", self.url)
            raise ValueError(f"Could not find series UUID for URL: {self.url}")

        self.json = self.client.get_series_data(self.uuid)

        if not self.json:
            crologger.error("Got an empty response. Series might not be available.")
            raise ValueError("Seriál není dostupný. Zkuste akci opakovat později.")

        self._attrs = self.json["data"]["attributes"]

        self.title = self._attrs["title"]
        self.parts = int(self._attrs["totalParts"])

        crologger.info("Opening series %s", self.title)
        crologger.info("Series ID : %s", self.uuid)
        crologger.info("Episodes: %s", self.parts)

        if not self.is_playable:
            msg = f"Series {self.title} is not available."
            crologger.error(msg)
            raise ValueError("Seriál není dostupný.")

        if not self.download_dir:
            self.download_dir = (
                DOWNLOAD_PATH
                / SERIES_DOWNLOAD_DIR
                / process_audiowork_title(self.title)
            )

    def __str__(self) -> str:
        return f"<Series: {self.title}>"

    def __repr__(self) -> str:
        return f"<Series: {self.title}>"

    @property
    def description(self) -> str | None:
        """
        A property method that returns the description of the series.
        """

        if not self._attrs:
            return None

        if self._attrs.get("description"):
            # Remove HTML tags and return the description
            return remove_html_tags(self._attrs.get("description"))
        return None

    @property
    def is_playable(self) -> bool:
        if self._attrs:
            return self._attrs.get("playable") is True

        return False

    @property
    def _episodes_url(self) -> str:
        """
        A property method that returns the API URL for episodes based on the data provided.
        Return type: str
        """
        return (
            self.json.get("data")
            .get("relationships")  # type: ignore
            .get("episodes")
            .get("links")
            .get("related")
        )

    def _fetch_episodes(self) -> list[dict]:
        """
        A private method to fetch episodes using `client` with a timeout.

        Returns:
            A list of dictionaries representing the fetched episodes.
        """
        return self.client.get_related_data(self._episodes_url).get("data")

    @property
    def episodes_data(self) -> list[dict]:
        """
        A property method that returns the episodes data as a list of dictionaries.
        """
        return self._fetch_episodes()

    @property
    def audio_formats(self) -> list[str | None]:
        episode = self.episodes_data[0]

        if not episode:
            return []

        audiolinks = episode["attributes"]["audioLinks"]

        formats = []
        for audiolink in audiolinks:
            formats.append(audiolink["variant"])
        return formats

    def list_all_series_episodes(self) -> list[str]:
        """
        Lists all series episodes and their details.

        Returns:
            A list of dictionaries containing episode information.
        """
        json_data = self.episodes_data

        all_parts = []

        for data in json_data:
            attrs = data.get("attributes")
            episode_num = attrs.get("part")  # type: ignore
            audio_link = get_audio_link_of_preferred_format(attrs)  # type: ignore

            all_parts.append(
                {
                    "uuid": data.get("id"),
                    "title": f"{episode_num}" + "-" + attrs.get("title"),  # type: ignore
                    "episode_num": episode_num,
                    "url": audio_link,
                    "since": attrs.get("since"),  # type: ignore
                }
            )

        return all_parts

    @property
    def downloaded_parts(self) -> int:
        """Returns the number of already downloaded parts."""
        if not self.download_dir:
            raise ValueError("Download dir is not set!")
        if not os.path.isdir(self.download_dir):
            return 0

        downloaded_parts = 0
        for part in range(1, self.parts + 1):
            if any(f.startswith(f"{part}-") for f in os.listdir(self.download_dir)):
                downloaded_parts += 1

        crologger.info("Parts downloaded: %s", downloaded_parts)
        crologger.info("Total parts: %s", self.parts)

        return downloaded_parts

    def already_exists(self) -> bool:
        crologger.info("Checking whether the series has been downloaded already...")
        return self.downloaded_parts == self.parts

    async def _download_episode(
        self, episode: dict, audio_format: Optional[AudioFormat], semaphore: asyncio.Semaphore, progress: Progress
    ) -> None:
        """Helper to download a single episode with semaphore control."""
        async with semaphore:
            download_to = self.download_dir
            audio_work = AudioWork(
                uuid=episode.get("uuid"),  # type: ignore
                audiowork_root=self.download_dir,
                audiowork_dir=download_to,
                title=episode.get("title"),  # type: ignore
                series=True,
                since=episode.get("since"),  # type: ignore
                client=self.client,
            )
            await audio_work.download(audio_format, progress=progress)

    async def download(
        self, audio_format: Optional[AudioFormat] = PREFERRED_AUDIO_FORMAT
    ) -> None:
        """Downloads all series episodes in parallel (limited by semaphore)."""
        if not self.download_dir:
            raise ValueError("Download dir is not set!")

        create_dir_if_does_not_exist(self.download_dir)
        create_a_file_if_does_not_exist(self.download_dir / ".series")

        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent downloads
        episodes = self.list_all_series_episodes()
        
        with Progress() as progress:
            tasks = [
                self._download_episode(episode, audio_format, semaphore, progress)
                for episode in episodes
            ]
            await asyncio.gather(*tasks)
