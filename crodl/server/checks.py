"""The "Zkontrolovat nové díly" run, and the state the pages show for it."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from crodl.library.service import LibraryService
from crodl.tools.logger import crologger

IDLE = "idle"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class CheckState:
    """How the last look for new parts went: the spinner, then a tick or a cross."""

    state: str = IDLE
    found: int = 0
    message: str = ""
    finished_at: Optional[datetime] = None

    @property
    def running(self) -> bool:
        return self.state == RUNNING


class UpdateChecker:
    """
    Runs the check in the background so the page can show that it is working.

    A check is a handful of API requests, so the request that starts one returns
    at once and the page spins until the state is no longer running. The timer
    in the app goes through the same door, which is why an automatic check shows
    up in the top bar as well.
    """

    def __init__(
        self, service_factory: Callable[[], LibraryService] = LibraryService
    ) -> None:
        self._service_factory = service_factory
        self.state = CheckState()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> CheckState:
        """Starts a check, unless one is running already."""
        if self.state.running:
            return self.state

        self.state = CheckState(state=RUNNING)
        # Keep the handle: a task nobody refers to may be collected mid-flight.
        self._task = asyncio.create_task(self.run())

        return self.state

    async def run(self) -> CheckState:
        """Runs the check in the caller's task and remembers the outcome."""
        self.state = CheckState(state=RUNNING)

        try:
            found = await self._service_factory().check_for_new_parts()
        except Exception as error:  # the page has to show that it went wrong
            crologger.error("The new-parts check failed: %s", error)
            self.state = CheckState(
                state=FAILED, message=str(error), finished_at=datetime.now()
            )
            return self.state

        self.state = CheckState(state=DONE, found=found, finished_at=datetime.now())

        return self.state


#: The one checker the app uses (the pages and the timer share it).
checker = UpdateChecker()
