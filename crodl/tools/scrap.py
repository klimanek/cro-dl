import json
import re

from bs4 import BeautifulSoup, Tag
from requests import Session

from crodl.settings import API_SERVER, PREFERRED_AUDIO_FORMAT
from crodl.tools.logger import crologger
from crodl.streams.utils import get_preferred_audio_format
from crodl.exceptions import (
    PageDoesNotExist,
    PlayerWrapperDoesNotExist,
    DataEntryDoesNotExist,
    AudioUUIDDoesNotExist,
    ShowUUIDDoesNotExist,
)

cro_session = Session()


def get_audio_uuid(site_url: str, session: Session) -> str:
    """Return the audio UUID from the site URL."""

    crologger.info("Opening URL: %s", site_url)
    response = session.get(site_url, timeout=5)

    if response.status_code == 404:
        crologger.error("The page %s does not exist.", site_url)
        raise PageDoesNotExist("The page %s does not exist.")

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


def get_show_uuid(site_url: str, session: Session) -> str:
    """Return the show's UUID from the site URL."""

    crologger.info("Opening URL: %s", site_url)
    response = session.get(site_url, timeout=5)

    if response.status_code == 404:
        crologger.error("%s does not exist.", site_url)
        raise PageDoesNotExist("The page does not exist.")

    # Show UUID and other attributes are in the div with class b-detail
    soup = BeautifulSoup(response.text, "html.parser")
    div = soup.find("div", {"class": "b-detail"})

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


def get_attributes(uuid: str, session: Session) -> dict:
    """Returns the attributes of the episode with the given UUID."""
    response = session.get(API_SERVER + "/episodes/" + uuid, timeout=5)

    if not response.json():
        err_msg = "API server sent an empty answer. Attributes are not known."
        crologger.error(err_msg)
        raise AttributeError(err_msg)
    if not response.json().get("data"):
        err_msg = "Data is empty, cannot find 'attributes' (uuid: %s)" % uuid
        crologger.error(err_msg)

        return {}

    return response.json().get("data").get("attributes")


def get_audio_link_of_preferred_format(attrs: dict) -> str | None:
    """Searches for an audio link of preferred audio format. If not found, returns None."""
    audio_links = attrs.get("audioLinks")

    if not audio_links:
        return None

    audio_variants = [link.get("variant") for link in audio_links]
    audio_formats = {link.get("variant"): link.get("url") for link in audio_links}

    if PREFERRED_AUDIO_FORMAT.value not in audio_variants:
        audio_format = get_preferred_audio_format(audio_variants)
    else:
        audio_format = PREFERRED_AUDIO_FORMAT

    return audio_formats.get(audio_format.value) if audio_format else None


def get_js_value_from_url(site_url: str, jsvar: str, session: Session) -> str | None:
    """Returns the value of a JavaScript variable from the given URL."""
    response = session.get(site_url)
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


def is_series(url: str, session: Session) -> bool:
    """Returns True, if the page contains a series."""
    return get_js_value_from_url(url, "siteEntityBundle", session) == "serial"


def get_series_id(site_url: str, session: Session) -> str | None:
    """Returns series ID, based on its URL"""

    return get_js_value_from_url(site_url, "contentId", session)


def is_show(url: str, session: Session) -> bool:
    """Returns True,  if the page contains a show."""
    return get_js_value_from_url(url, "siteEntityBundle", session) == "show"


# "siteEntityBundle":"serialPart"
