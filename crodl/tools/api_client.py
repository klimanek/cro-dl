import json
import re
from typing import Optional, Dict, Any

import cloudscraper
from bs4 import BeautifulSoup, Tag
from requests import Session

from crodl.exceptions import (
    AudioUUIDDoesNotExist,
    DataEntryDoesNotExist,
    PageDoesNotExist,
    PlayerWrapperDoesNotExist,
    ShowUUIDDoesNotExist,
)
from crodl.settings import API_SERVER, TIMEOUT
from crodl.tools.logger import crologger


class CroAPIClient:
    """
    Client for interacting with mujrozhlas.cz API and website.
    Uses cloudscraper to bypass Cloudflare challenges.
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session or cloudscraper.create_scraper()

    def get_audio_uuid(self, site_url: str) -> str:
        """Return the audio UUID from the site URL."""
        crologger.info("Opening URL: %s", site_url)
        response = self.session.get(site_url, timeout=TIMEOUT)

        if response.status_code == 404:
            crologger.error("The page %s does not exist.", site_url)
            raise PageDoesNotExist(f"The page {site_url} does not exist.")

        soup = BeautifulSoup(response.text, "html.parser")

        # UUID and other attributes are in the player-wrapper
        player_wrapper = soup.select(".player-wrapper")

        if not player_wrapper:
            raise PlayerWrapperDoesNotExist(
                "Player not found. Maybe it is a show and not a series?"
            )

        # Data are stored in a list, we extract it as bs4.Tag
        player_data: Tag = player_wrapper[0]
        data_entry: str = str(player_data.get("data-entry", ""))
        crologger.info("Getting data-entry values.")

        if not data_entry:
            err_msg = "Attribute data-entry not found."
            crologger.error(err_msg)
            raise DataEntryDoesNotExist(err_msg)

        json_data_entry = json.loads(data_entry)
        crologger.info("Parsing JSON.")

        uuid = json_data_entry.get("uuid", None)
        crologger.info("Getting UUID... %s", uuid)

        if not uuid:
            err_msg = "The program does not exist or other fatal error occured."
            crologger.error(err_msg)
            raise AudioUUIDDoesNotExist(err_msg)

        return uuid

    def get_show_uuid(self, site_url: str) -> str:
        """Return the show's UUID from the site URL."""
        crologger.info("Opening URL: %s", site_url)
        response = self.session.get(site_url, timeout=TIMEOUT)

        if response.status_code == 404:
            crologger.error("%s does not exist.", site_url)
            raise PageDoesNotExist("The page does not exist.")

        # Show UUID and other attributes are in the div with class b-detail
        soup = BeautifulSoup(response.text, "html.parser")
        div = soup.find("div", {"class": "b-detail"})

        if not div:
            err_msg = "Detail div not found. Maybe it is not a show page?"
            crologger.error(err_msg)
            raise PlayerWrapperDoesNotExist(err_msg)

        crologger.info("Getting data-entry values.")

        data_entry: str = str(div.get("data-entry", ""))  # type: ignore

        if not data_entry:
            err_msg = "Attribute data-entry not found."
            crologger.error(err_msg)
            raise DataEntryDoesNotExist(err_msg)

        json_data_entry = json.loads(data_entry)
        crologger.info("Parsing JSON.")

        uuid = json_data_entry.get("show-uuid", None)
        crologger.info("Getting UUID... %s", uuid)

        if not uuid:
            err_msg = "Show does not exist or other fatal error occured."
            crologger.error(err_msg)
            raise ShowUUIDDoesNotExist(err_msg)

        return uuid

    def get_js_value_from_url(self, site_url: str, jsvar: str) -> Optional[str]:
        """Returns the value of a JavaScript variable from the given URL."""
        response = self.session.get(site_url)
        err_msg = f"Variable {jsvar} was not found."

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            script_tags = soup.find_all("script")

            for script in script_tags:
                if jsvar in script.text:
                    pattern = re.compile(rf'"{jsvar}":"([^"]+)"')
                    match = pattern.search(script.text)

                    if match:
                        return match.group(1)

            crologger.error(err_msg)
            return None

        crologger.error("Server error.")
        return None

    def get_series_id(self, site_url: str) -> Optional[str]:
        """Returns series ID, based on its URL"""
        return self.get_js_value_from_url(site_url, "contentId")

    def is_series(self, url: str) -> bool:
        """Returns True, if the page contains a series."""
        return self.get_js_value_from_url(url, "siteEntityBundle") == "serial"

    def is_show(self, url: str) -> bool:
        """Returns True, if the page contains a show."""
        return self.get_js_value_from_url(url, "siteEntityBundle") == "show"

    def get_episode_data(self, uuid: str) -> Dict[str, Any]:
        """Returns the data of the episode with the given UUID."""
        response = self.session.get(f"{API_SERVER}/episodes/{uuid}", timeout=TIMEOUT)

        if not response.json():
            err_msg = "API server sent an empty answer."
            crologger.error(err_msg)
            raise AttributeError(err_msg)

        if not response.json().get("data"):
            err_msg = f"Data are empty (uuid: {uuid})."
            crologger.error(err_msg)
            return {}

        return response.json()

    def get_series_data(self, uuid: str) -> Dict[str, Any]:
        """Returns the data of the series with the given UUID."""
        response = self.session.get(f"{API_SERVER}/serials/{uuid}", timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    def get_show_data(self, uuid: str) -> Dict[str, Any]:
        """Returns the data of the show with the given UUID."""
        response = self.session.get(f"{API_SERVER}/shows/{uuid}", timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    def get_related_data(self, url: str) -> Dict[str, Any]:
        """Returns related data from a given URL (e.g. episodes of a series)."""
        response = self.session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    def search(self, query: str) -> Dict[str, Any]:
        """Searches for programs, episodes or series by a query string."""
        crologger.info("Searching for: %s", query)
        response = self.session.get(f"{API_SERVER}/search?q={query}", timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
