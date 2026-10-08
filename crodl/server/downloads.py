"""Downloads started from the web UI.

A download takes minutes, so it runs as a background task and the UI watches a
job: the pages refresh themselves and the JSON API answers the same thing.

Progress is read from the work itself (`downloaded_parts` against the number of
parts the API reported) rather than pushed out of the core by a callback: the
core knows about files, not about HTTP, and the CLI's progress display (`rich`)
is exactly that - the CLI's.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from uuid import uuid4

from rich.progress import Progress

from crodl.facade import CroDL
from crodl.library.service import LibraryService
from crodl.tools.logger import crologger


def _parts_of(content: Any) -> int:
    """How many parts the work has, as far as the API has told us."""
    parts = getattr(content, "parts", 0)
    if not parts:
        episodes = getattr(content, "episodes", None)
        parts = getattr(episodes, "count", 0)

    return int(parts or 1)


def _parts_downloaded(content: Any) -> int:
    """How many parts the download has written so far."""
    counter = getattr(content, "downloaded_parts", None)

    if counter is None:  # a single work: one file, or none yet
        return 1 if content.already_exists() else 0

    return int(counter)


@dataclass
class DownloadJob:
    """One download the UI started, with what the UI wants to show about it."""

    id: str
    url: str
    state: str = "running"  # running | done | failed
    title: str = ""
    message: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    #: The work being downloaded, and the handle on the running task.
    content: Any = field(default=None, repr=False)
    task: Optional[asyncio.Task] = field(default=None, repr=False)

    def as_dict(self) -> dict[str, Any]:
        """The job as the pages and the JSON API report it."""
        done, total = self._progress()

        return {
            "id": self.id,
            "url": self.url,
            "state": self.state,
            "title": self.title,
            "message": self.message,
            "done": done,
            "total": total,
            "percent": round(done / total * 100) if total else 0,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": (
                self.finished_at.isoformat(timespec="seconds")
                if self.finished_at
                else None
            ),
        }

    def _progress(self) -> tuple[int, int]:
        """Parts on disk against parts expected, read from the work on demand."""
        if self.content is None:
            return 0, 0

        try:
            return _parts_downloaded(self.content), _parts_of(self.content)
        except Exception:  # the work may be mid-write; progress is a nicety
            return 0, 0


def default_facade() -> CroDL:
    """The facade a web download runs through, with the library attached."""
    return CroDL(library=LibraryService())


class DownloadManager:
    """Runs downloads in the background and keeps the last few to look at."""

    #: Enough to check on recent downloads without growing without bound.
    MAX_JOBS = 20

    def __init__(self, facade_factory: Callable[[], CroDL] = default_facade) -> None:
        self._facade_factory = facade_factory
        self._jobs: dict[str, DownloadJob] = {}

    def start(self, url: str) -> DownloadJob:
        """Queues a download and returns the job the caller can watch."""
        job = DownloadJob(id=uuid4().hex[:12], url=url)
        self._remember(job)
        # Keep the handle: a task nobody refers to may be collected mid-flight.
        job.task = asyncio.create_task(self._run(job))

        return job

    def get(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)

    def jobs(self) -> list[DownloadJob]:
        """The jobs, newest first."""
        return list(reversed(self._jobs.values()))

    async def _run(self, job: DownloadJob) -> None:
        """The download itself - the only part that touches the network."""
        facade = self._facade_factory()

        try:
            content = await facade.get_content(job.url)
            job.title = content.title
            job.content = content

            # `rich` is the CLI's display; the web reads the work's counters, so
            # a disabled one only keeps progress bars out of the server console.
            await facade.download(content, progress=Progress(disable=True))

            job.state = "done"
            crologger.info("Web download finished: %s", job.title)
        except Exception as error:  # the UI has to show why it failed
            job.state = "failed"
            job.message = str(error)
            crologger.error("Web download failed for %s: %s", job.url, error)
        finally:
            job.finished_at = datetime.now()

    def _remember(self, job: DownloadJob) -> None:
        """Keeps the newest jobs; the oldest fall off the end."""
        self._jobs[job.id] = job

        while len(self._jobs) > self.MAX_JOBS:
            self._jobs.pop(next(iter(self._jobs)))


#: The one manager the app uses: the pages and the JSON API share it.
downloads = DownloadManager()
