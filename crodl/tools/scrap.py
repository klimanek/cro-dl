from requests import Session

from crodl.settings import PREFERRED_AUDIO_FORMAT
from crodl.tools.api_client import CroAPIClient
from crodl.streams.utils import get_preferred_audio_format

cro_session = Session()
_api_client = CroAPIClient(session=cro_session)


def get_audio_uuid(site_url: str, session) -> str:
    """Return the audio UUID from the site URL."""
    client = _api_client if session == cro_session else CroAPIClient(session=session)
    return client.get_audio_uuid(site_url)


def get_show_uuid(site_url: str, session) -> str:
    """Return the show's UUID from the site URL."""
    client = _api_client if session == cro_session else CroAPIClient(session=session)
    return client.get_show_uuid(site_url)


def get_json(uuid: str, session: Session) -> dict:
    """Returns the attributes of the episode with the given UUID."""
    client = _api_client if session == cro_session else CroAPIClient(session=session)
    return client.get_episode_data(uuid)


def get_attributes(uuid: str, session: Session) -> dict:
    """Returns the json resp. on the episode with the given UUID."""
    json_data = get_json(uuid, session)
    try:
        attrs = json_data["data"]["attributes"]
    except (KeyError, TypeError):
        attrs = {}
    return attrs if attrs else {}


def get_audio_link_of_preferred_format(attrs: dict) -> str | None:
    """Searches for an audio link of preferred audio format.
    If not found, returns None.
    """
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


def get_js_value_from_url(site_url: str, jsvar: str, session) -> str | None:
    """Returns the value of a JavaScript variable from the given URL."""
    client = _api_client if session == cro_session else CroAPIClient(session=session)
    return client.get_js_value_from_url(site_url, jsvar)


def is_series(url: str, session) -> bool:
    """Returns True, if the page contains a series."""
    return get_js_value_from_url(url, "siteEntityBundle", session) == "serial"


def get_series_id(site_url: str, session) -> str | None:
    """Returns series ID, based on its URL"""
    return get_js_value_from_url(site_url, "contentId", session)


def is_show(url: str, session) -> bool:
    """Returns True,  if the page contains a show."""
    return get_js_value_from_url(url, "siteEntityBundle", session) == "show"
