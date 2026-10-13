"""Downloads the web UI starts: they run in the background, the UI watches them."""

import asyncio
import unittest
from pathlib import Path

from crodl.library.updates import NewPart
from crodl.program.content import Collection
from crodl.server.downloads import DownloadManager

URL = "https://www.mujrozhlas.cz/cetba-na-pokracovani/bohumil-hrabal"


class FakeSeries:
    """A Series-like work: parts the API reported, parts already written."""

    def __init__(self, title: str = "Seriál", parts: int = 3, on_disk: int = 0) -> None:
        self.title = title
        self.parts = parts
        self.on_disk = on_disk

    @property
    def downloaded_parts(self) -> int:
        return self.on_disk


class FakeSingleWork:
    """An AudioWork-like work: no part counter, only "is it there yet"."""

    def __init__(self, title: str = "Dílo", downloaded: bool = False) -> None:
        self.title = title
        self.downloaded = downloaded

    def already_exists(self) -> bool:
        return self.downloaded


class FakeFacade:
    """The facade a job runs through, with the download under the test's control."""

    def __init__(self, content=None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.progress = None
        self.parts: list[tuple[str, str, int | None]] = []
        self.part_error: Exception | None = None

    async def get_content(self, url: str):
        if self.error is not None:
            raise self.error

        return self.content

    async def download(self, content, audio_format=None, progress=None) -> None:
        self.progress = progress
        self.started.set()
        await self.finish.wait()

    async def download_part(
        self, uuid, title, *, part=None, directory=None, collection=None, progress=None
    ) -> None:
        """Fetches one part by uuid, the way the real facade does."""
        if self.part_error is not None:
            raise self.part_error

        self.parts.append((uuid, title, part))


def manager_for(facade: FakeFacade) -> DownloadManager:
    return DownloadManager(facade_factory=lambda: facade)


class TestDownloadManager(unittest.IsolatedAsyncioTestCase):
    async def test_a_job_runs_in_the_background_and_reports_progress(self):
        facade = FakeFacade(FakeSeries())
        manager = manager_for(facade)

        job = manager.start(URL)
        await facade.started.wait()

        state = job.as_dict()
        self.assertEqual(state["state"], "running")
        self.assertEqual(state["title"], "Seriál")
        self.assertEqual((state["done"], state["total"]), (0, 3))

        facade.content.on_disk = 2
        self.assertEqual(job.as_dict()["done"], 2)
        self.assertEqual(job.as_dict()["percent"], 67)

        facade.finish.set()
        await job.task

        finished = job.as_dict()
        self.assertEqual(finished["state"], "done")
        self.assertEqual(finished["done"], 2)
        self.assertIsNotNone(finished["finished_at"])

    async def test_the_cli_progress_display_is_kept_quiet(self):
        # The web reads the work's own counters; a live `rich` display would just
        # scribble over the server's console.
        facade = FakeFacade(FakeSeries(parts=1))
        manager = manager_for(facade)

        job = manager.start(URL)
        await facade.started.wait()

        self.assertTrue(facade.progress.disable)
        facade.finish.set()
        await job.task

    async def test_a_single_work_counts_as_one_part(self):
        facade = FakeFacade(FakeSingleWork())
        manager = manager_for(facade)

        job = manager.start(URL)
        await facade.started.wait()

        self.assertEqual(job.as_dict()["total"], 1)
        self.assertEqual(job.as_dict()["done"], 0)

        facade.content.downloaded = True
        self.assertEqual(job.as_dict()["done"], 1)

        facade.finish.set()
        await job.task

    async def test_a_failed_download_keeps_the_reason_for_the_ui(self):
        manager = manager_for(FakeFacade(error=ValueError("Unsupported domain")))

        job = manager.start(URL)
        await job.task

        state = job.as_dict()
        self.assertEqual(state["state"], "failed")
        self.assertIn("Unsupported domain", state["message"])
        self.assertIsNotNone(state["finished_at"])

    async def test_jobs_are_listed_newest_first(self):
        facade = FakeFacade(FakeSeries(parts=1))
        facade.finish.set()
        manager = manager_for(facade)

        first = manager.start(URL)
        await first.task
        second = manager.start(URL)
        await second.task

        self.assertEqual([job.id for job in manager.jobs()], [second.id, first.id])

    async def test_only_the_newest_jobs_are_kept(self):
        facade = FakeFacade(FakeSeries(parts=1))
        facade.finish.set()
        manager = manager_for(facade)

        for _ in range(DownloadManager.MAX_JOBS + 3):
            await manager.start(URL).task

        self.assertEqual(len(manager.jobs()), DownloadManager.MAX_JOBS)

    async def test_an_unknown_job_is_not_there(self):
        self.assertIsNone(manager_for(FakeFacade()).get("nope"))


class TestJobWithoutContent(unittest.IsolatedAsyncioTestCase):
    async def test_progress_is_zero_until_the_work_is_known(self):
        facade = FakeFacade(FakeSeries())
        manager = manager_for(facade)

        job = manager.start(URL)
        # Nothing has been resolved yet: the API has not answered.
        self.assertEqual(job.as_dict()["percent"], 0)

        await facade.started.wait()
        facade.finish.set()
        await job.task


class TestNewPartJobs(unittest.IsolatedAsyncioTestCase):
    """A job that fetches the parts a work gained (no single work to look at)."""

    def _facade(self) -> "FakeFacade":
        return FakeFacade()

    def _collection(self) -> Collection:
        return Collection(uuid="series-1", type="series", title="Seriál")

    async def test_each_missing_part_is_fetched_and_counted(self):
        facade = self._facade()
        manager = manager_for(facade)
        parts = [NewPart(uuid="u-1", title="Díl", part=1), NewPart("u-2", "Díl", 2)]

        job = manager.start_missing(
            "Seriál",
            parts,
            directory=Path("/tmp/Seriál"),
            collection=self._collection(),
        )
        await job.task

        state = job.as_dict()
        self.assertEqual(state["state"], "done")
        self.assertEqual((state["done"], state["total"]), (2, 2))
        self.assertEqual([called[0] for called in facade.parts], ["u-1", "u-2"])
        self.assertEqual(job.title, "Seriál - nové díly")

    async def test_a_part_that_fails_stops_the_job_with_the_reason(self):
        facade = self._facade()
        facade.part_error = OSError("the stream is gone")
        manager = manager_for(facade)

        job = manager.start_missing(
            "Seriál",
            [NewPart("u-1", "Díl", 1)],
            directory=Path("/tmp/Seriál"),
            collection=self._collection(),
        )
        await job.task

        state = job.as_dict()
        self.assertEqual(state["state"], "failed")
        self.assertIn("the stream is gone", state["message"])


if __name__ == "__main__":
    unittest.main()
