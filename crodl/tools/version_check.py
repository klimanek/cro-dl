"""Is there a newer cro-dl on PyPI?

The answer is cached for a day in the download folder, so the CLI and the web
library both ask once and a failed request never breaks a run.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from packaging.version import InvalidVersion, Version

from crodl import __version__
from crodl.settings import DOWNLOAD_PATH
from crodl.tools.logger import crologger

PYPI_URL = "https://pypi.org/pypi/cro-dl/json"
CACHE_PATH = DOWNLOAD_PATH / ".version-check.json"
CHECK_EVERY = timedelta(days=1)
TIMEOUT = 2.0


@dataclass(frozen=True)
class NewVersion:
    """The installed version and the newer one PyPI reports."""

    current: str
    latest: str


_known: Optional[NewVersion] = None


def known() -> Optional[NewVersion]:
    """What the last check in this process found, if anything."""
    return _known


def is_newer(latest: str, current: str) -> bool:
    """Whether `latest` is a later release than `current`."""
    try:
        return Version(str(latest)) > Version(str(current))
    except InvalidVersion:
        return False


def _cached(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    return data if isinstance(data, dict) else None


def _fresh(cache: Optional[dict], now: datetime) -> bool:
    if not cache:
        return False

    try:
        checked = datetime.fromisoformat(str(cache.get("checked_at")))
    except ValueError:
        return False

    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)

    return now - checked < CHECK_EVERY


def _remember(path: Path, latest: str, now: datetime) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"checked_at": now.isoformat(), "latest": latest}),
            encoding="utf-8",
        )
    except OSError as error:  # a read-only home is not a reason to fail
        crologger.info("Could not cache the version check: %s", error)


def _latest(timeout: float) -> Optional[str]:
    try:
        response = requests.get(
            PYPI_URL,
            timeout=timeout,
            headers={"User-Agent": f"cro-dl/{__version__}"},
        )
        response.raise_for_status()
        latest = response.json().get("info", {}).get("version")
    except (requests.RequestException, ValueError, AttributeError) as error:
        crologger.info("Could not check PyPI for a newer cro-dl: %s", error)
        return None

    return str(latest) if latest else None


def check(
    current: str = __version__,
    cache: Path = CACHE_PATH,
    timeout: float = TIMEOUT,
) -> Optional[NewVersion]:
    """The newer release on PyPI, if there is one; None when up to date."""
    global _known
    now = datetime.now(timezone.utc)
    stored = _cached(cache)
    latest = stored.get("latest") if stored else None

    if not _fresh(stored, now):
        fetched = _latest(timeout)
        if fetched is not None:
            latest = fetched
            _remember(cache, fetched, now)

    _known = (
        NewVersion(current=current, latest=str(latest))
        if latest and is_newer(str(latest), current)
        else None
    )
    return _known


async def refresh() -> Optional[NewVersion]:
    """Checks for a newer release without blocking the caller's loop."""
    return await asyncio.to_thread(check)


async def watch() -> None:
    """Refreshes at start and then once a day, for a long-running server."""
    while True:
        await refresh()
        await asyncio.sleep(CHECK_EVERY.total_seconds())
