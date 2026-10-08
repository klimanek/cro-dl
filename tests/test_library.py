import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest import mock

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from crodl.library.artwork import artwork_path
from crodl.library.models import Episode, Series, Show, Station
from crodl.library.repository import (
    LibraryRepository,
    SqliteLibraryRepository,
    parse_since,
    to_naive_utc,
)
from crodl.library.scan import LibraryScan
from crodl.library.service import LibraryService
from crodl.program.content import Collection

# Engines created by `make_repo`, disposed by `InMemoryLibraryTestCase`.
_ENGINES: list[AsyncEngine] = []


class FakeWork:
    """Minimal stand-in for a downloaded AudioWork (matches DownloadedWork)."""

    def __init__(
        self,
        uuid: Optional[str] = "u-1",
        title: str = "Dílo",
        since: str = "2024-08-14T18:05:00+02:00",
        description: Optional[str] = "Popis",
        author: Optional[str] = "Autor",
        audio_formats: Optional[list[str]] = None,
        short_title: Optional[str] = "Krátce",
        part: Optional[int] = 3,
        duration: Optional[int] = 3229,
        asset_url: Optional[str] = None,
    ) -> None:
        self.uuid = uuid
        self.title = title
        self.since = since
        self.description = description
        self.author = author
        self.audio_formats = ["mp3", "hls"] if audio_formats is None else audio_formats
        self.short_title = short_title
        self.part = part
        self.duration = duration
        self.asset_url = asset_url


async def make_repo() -> SqliteLibraryRepository:
    """A repository over a fresh in-memory database (never the real file)."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Disposed by the test case: a leaked engine complains once its event loop
    # is gone, and that lands in whatever test happens to run next.
    _ENGINES.append(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    return SqliteLibraryRepository(session_factory=factory)


class InMemoryLibraryTestCase(unittest.IsolatedAsyncioTestCase):
    """Closes the in-memory engines created by `make_repo`."""

    async def asyncTearDown(self) -> None:
        while _ENGINES:
            await _ENGINES.pop().dispose()


class TestSqliteLibraryRepository(InMemoryLibraryTestCase):
    async def test_save_download_stores_a_row(self):
        repo = await make_repo()
        path = Path("/tmp/library/1 - Díl.mp3")

        episode = await repo.save_download(FakeWork(), path, audio_format="mp3")

        self.assertIsNotNone(episode)
        downloads = await repo.get_all_downloads()
        self.assertEqual(len(downloads), 1)

        stored = downloads[0]
        self.assertEqual(stored.uuid, "u-1")
        self.assertEqual(stored.title, "Dílo")
        self.assertEqual(stored.short_title, "Krátce")
        self.assertEqual(stored.part, 3)
        self.assertEqual(stored.author, "Autor")
        self.assertEqual(stored.description, "Popis")
        self.assertEqual(stored.duration, 3229)
        self.assertEqual(stored.local_path, str(path))
        self.assertEqual(stored.audio_format, "mp3")
        self.assertEqual(
            stored.broadcast_at, to_naive_utc(parse_since("2024-08-14T18:05:00+02:00"))
        )
        self.assertIsInstance(stored.downloaded_at, datetime)

    async def test_variants_and_raw_since_are_kept_as_json(self):
        repo = await make_repo()
        await repo.save_download(FakeWork(), Path("/tmp/a.mp3"))

        stored = (await repo.get_all_downloads())[0]
        self.assertEqual(stored.meta["variants"], ["mp3", "hls"])
        self.assertEqual(stored.meta["since"], FakeWork().since)

    async def test_saving_the_same_uuid_updates_the_row(self):
        repo = await make_repo()

        await repo.save_download(FakeWork(title="Starý název"), Path("/tmp/a.mp3"))
        await repo.save_download(FakeWork(title="Nový název"), Path("/tmp/b.mp3"))

        downloads = await repo.get_all_downloads()
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0].title, "Nový název")
        self.assertEqual(downloads[0].local_path, "/tmp/b.mp3")

    async def test_work_without_uuid_is_not_stored(self):
        repo = await make_repo()

        with mock.patch("crodl.library.repository.crologger") as mock_logger:
            episode = await repo.save_download(FakeWork(uuid=None), Path("/tmp/a.mp3"))

        self.assertIsNone(episode)
        self.assertEqual(await repo.get_all_downloads(), [])
        mock_logger.warning.assert_called_once()

    async def test_unparsable_since_is_stored_as_none(self):
        repo = await make_repo()
        await repo.save_download(FakeWork(since="not a date"), Path("/tmp/a.mp3"))

        self.assertIsNone((await repo.get_all_downloads())[0].broadcast_at)


class TestParseSince(unittest.TestCase):
    def test_parses_iso_with_offset(self):
        value = "2024-08-14T18:05:00+02:00"
        self.assertEqual(parse_since(value), datetime.fromisoformat(value))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_since(""))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_since("not a date"))


class TestEpisodeModel(unittest.TestCase):
    def test_defaults(self):
        episode = Episode(uuid="u-1", title="Dílo", local_path="/tmp/a.mp3")

        self.assertEqual(episode.meta, {})
        self.assertIsInstance(episode.downloaded_at, datetime)
        self.assertIsNone(episode.broadcast_at)
        self.assertIsNone(episode.image_path)
        self.assertIsNone(episode.audio_format)
        self.assertIsNone(episode.short_title)
        self.assertIsNone(episode.part)
        self.assertIsNone(episode.duration)


class TestRepositoryProtocol(unittest.TestCase):
    def test_sqlite_repository_implements_the_protocol(self):
        self.assertIsInstance(SqliteLibraryRepository(), LibraryRepository)

    def test_library_service_satisfies_the_download_store(self):
        from crodl.library.repository import DownloadStore

        self.assertIsInstance(LibraryService(), DownloadStore)


class TestLibraryQueries(InMemoryLibraryTestCase):
    async def test_episodes_are_grouped_by_show_and_series(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="a"), Path("/tmp/a.mp3"), show_id="show-1"
        )
        await repo.save_download(
            FakeWork(uuid="b"), Path("/tmp/b.mp3"), series_id="ser-1"
        )
        await repo.save_download(FakeWork(uuid="c"), Path("/tmp/c.mp3"))

        self.assertEqual(
            {e.uuid for e in await repo.get_all_episodes()}, {"a", "b", "c"}
        )
        self.assertEqual(
            {e.uuid for e in await repo.get_episodes_by_show("show-1")}, {"a"}
        )
        self.assertEqual(
            {e.uuid for e in await repo.get_episodes_by_series("ser-1")}, {"b"}
        )
        episode = await repo.get_episode("b")
        self.assertIsNotNone(episode)

    async def test_shows_and_series_are_stored_and_read_back(self):
        repo = await make_repo()
        await repo.save_show(Show(uuid="s1", title="Pořad"))
        await repo.save_series(Series(uuid="r1", title="Seriál"))
        await repo.save_station(Station(id="vltava", title="Vltava"))

        self.assertEqual([s.title for s in await repo.get_all_shows()], ["Pořad"])
        self.assertEqual([s.title for s in await repo.get_all_series()], ["Seriál"])
        show = await repo.get_show("s1")
        series = await repo.get_series("r1")
        self.assertIsNotNone(show)
        self.assertIsNotNone(series)


class TestEpisodeLookupAndLinking(InMemoryLibraryTestCase):
    """What the disk scan needs: find a file's row, then file it under a work."""

    async def test_an_episode_is_found_by_its_path(self):
        repo = await make_repo()
        path = Path("/tmp/library/1 - Díl.mp3")
        await repo.save_download(FakeWork(uuid="cro-uuid"), path)

        found = await repo.find_episode_by_path(path)

        self.assertIsNotNone(found)
        self.assertEqual(found.uuid, "cro-uuid")  # type: ignore[union-attr]
        self.assertIsNone(await repo.find_episode_by_path(Path("/tmp/other.mp3")))

    async def test_linking_files_an_unlinked_episode_under_a_work(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="part-1"), Path("/tmp/library/1 - Díl.mp3")
        )

        await repo.link_episode(
            "part-1", Collection(uuid="series-1", type="series", title="Seriál")
        )

        self.assertEqual(
            [e.uuid for e in await repo.get_episodes_by_series("series-1")], ["part-1"]
        )
        self.assertIsNotNone(await repo.get_series("series-1"))

    async def test_linking_a_show_files_it_as_a_show(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="part-1"), Path("/tmp/library/1 - Díl.mp3")
        )

        await repo.link_episode(
            "part-1", Collection(uuid="show-1", type="show", title="Pořad")
        )

        self.assertEqual(
            [e.uuid for e in await repo.get_episodes_by_show("show-1")], ["part-1"]
        )

    async def test_an_episode_that_already_has_a_collection_keeps_it(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="part-1"), Path("/tmp/a.mp3"), series_id="cro-series"
        )

        await repo.link_episode(
            "part-1", Collection(uuid="folder-hash", type="series", title="Složka")
        )

        episode = await repo.get_episode("part-1")
        self.assertEqual(episode.series_id, "cro-series")  # type: ignore[union-attr]
        self.assertIsNone(await repo.get_series("folder-hash"))

    async def test_linking_ignores_unknown_episodes_and_missing_collections(self):
        repo = await make_repo()
        await repo.link_episode(
            "missing", Collection(uuid="series-1", type="series", title="Seriál")
        )
        await repo.save_download(FakeWork(uuid="part-1"), Path("/tmp/a.mp3"))
        await repo.link_episode("part-1", None)

        self.assertIsNone(await repo.get_series("series-1"))
        episode = await repo.get_episode("part-1")
        self.assertIsNone(episode.series_id)  # type: ignore[union-attr]


class TestLibraryScan(InMemoryLibraryTestCase):
    async def test_scan_imports_audio_files_only(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "3 - Název dílu.mp3").write_bytes(b"x")
            (folder / "Samostatné dílo.aac").write_bytes(b"x")
            (folder / "cover.jpg").write_bytes(b"x")
            chunks = folder / ".chunks-x"
            chunks.mkdir()
            (chunks / "chunk.mp3").write_bytes(b"x")

            results = await LibraryScan(
                repository=repo, download_path=folder
            ).sync_all()

        self.assertEqual(results, {"success": 2, "failed": 0})

        rows = {episode.title: episode for episode in await repo.get_all_episodes()}
        self.assertEqual(set(rows), {"Název dílu", "Samostatné dílo"})
        self.assertEqual(rows["Název dílu"].part, 3)
        self.assertEqual(rows["Název dílu"].audio_format, "mp3")
        self.assertTrue(rows["Název dílu"].is_manual)
        self.assertIsNone(rows["Samostatné dílo"].part)

    async def test_rescanning_updates_instead_of_duplicating(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "1 - Díl.mp3").write_bytes(b"x")
            scan = LibraryScan(repository=repo, download_path=Path(tmp))

            await scan.sync_all()
            await scan.sync_all()
            episodes = await repo.get_all_episodes()

        self.assertEqual(len(episodes), 1)


class TestLibraryService(unittest.IsolatedAsyncioTestCase):
    async def test_artwork_is_fetched_and_its_path_stored(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        cover = Path("/tmp/library/3 - Díl.jpg")

        with mock.patch(
            "crodl.library.artwork.download_image",
            new=mock.AsyncMock(return_value=cover),
        ) as download:
            episode = await service.save_download(
                FakeWork(asset_url="https://example.com/cover.jpg"),
                Path("/tmp/library/3 - Díl.mp3"),
                audio_format="mp3",
            )

        download.assert_awaited_once_with(
            "https://example.com/cover.jpg", Path("/tmp/library/3 - Díl.jpg")
        )
        self.assertIsNotNone(episode)
        self.assertEqual(
            str(episode.image_path),  # type: ignore[union-attr]
            str(cover),
        )

    async def test_without_an_asset_url_no_image_is_fetched(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)

        with mock.patch(
            "crodl.library.artwork.download_image", new=mock.AsyncMock()
        ) as download:
            episode = await service.save_download(FakeWork(), Path("/tmp/a.mp3"))

        download.assert_not_awaited()
        self.assertIsNone(episode.image_path)  # type: ignore[union-attr]

    async def test_an_episode_links_to_the_work_it_belongs_to(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)

        episode = await service.save_download(
            FakeWork(uuid="part-1"),
            Path("/tmp/library/1 - Díl.mp3"),
            collection=Collection(
                uuid="series-1", type="series", title="Seriál", description="Popis"
            ),
        )

        self.assertIsNotNone(episode)
        self.assertEqual(episode.series_id, "series-1")  # type: ignore[union-attr]
        self.assertIsNone(episode.show_id)  # type: ignore[union-attr]
        stored = await repo.get_series("series-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.title, "Seriál")  # type: ignore[union-attr]
        self.assertEqual(
            [e.uuid for e in await repo.get_episodes_by_series("series-1")], ["part-1"]
        )

    async def test_a_show_is_stored_as_a_show(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)

        episode = await service.save_download(
            FakeWork(uuid="part-1"),
            Path("/tmp/library/1 - Díl.mp3"),
            collection=Collection(uuid="show-1", type="show", title="Pořad"),
        )

        self.assertEqual(episode.show_id, "show-1")  # type: ignore[union-attr]
        self.assertIsNone(episode.series_id)  # type: ignore[union-attr]
        self.assertEqual([e.title for e in await repo.get_all_shows()], ["Pořad"])


class TestSharedCover(InMemoryLibraryTestCase):
    """The parts of one work share a single cover instead of one each."""

    url = "https://example.com/cover.jpg"
    directory = Path("/tmp/library/Seriál")

    def _collection(self) -> Collection:
        return Collection(
            uuid="series-1",
            type="series",
            title="Seriál",
            shared_asset_url=self.url,
        )

    @staticmethod
    def _download_image():
        """Stands in for the real downloader, which writes the file."""

        async def download(url, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"image")
            return target

        return mock.AsyncMock(side_effect=download)

    async def test_the_cover_is_downloaded_once_for_all_parts(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        download = self._download_image()

        with mock.patch("crodl.library.artwork.download_image", new=download):
            first = await service.save_download(
                FakeWork(uuid="part-1"),
                self.directory / "1 - Díl.mp3",
                collection=self._collection(),
            )
            second = await service.save_download(
                FakeWork(uuid="part-2"),
                self.directory / "2 - Díl.mp3",
                collection=self._collection(),
            )

        download.assert_awaited_once_with(self.url, self.directory / "cover.jpg")
        self.assertEqual(str(first.image_path), str(self.directory / "cover.jpg"))  # type: ignore[union-attr]
        self.assertEqual(str(second.image_path), str(self.directory / "cover.jpg"))  # type: ignore[union-attr]

    async def test_a_cover_already_on_disk_is_not_downloaded_again(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        cover = self.directory / "cover.jpg"
        cover.parent.mkdir(parents=True, exist_ok=True)
        cover.write_bytes(b"image")
        self.addCleanup(cover.unlink, missing_ok=True)

        with mock.patch(
            "crodl.library.artwork.download_image", new=mock.AsyncMock()
        ) as download:
            episode = await service.save_download(
                FakeWork(uuid="part-1"),
                self.directory / "1 - Díl.mp3",
                collection=self._collection(),
            )

        download.assert_not_awaited()
        self.assertEqual(str(episode.image_path), str(cover))  # type: ignore[union-attr]

    async def test_parts_of_separate_works_keep_an_image_each(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        download = self._download_image()
        collection = Collection(uuid="series-1", type="series", title="Seriál")

        with mock.patch("crodl.library.artwork.download_image", new=download):
            await service.save_download(
                FakeWork(uuid="part-1", asset_url=self.url),
                self.directory / "1 - Díl.mp3",
                collection=collection,
            )
            await service.save_download(
                FakeWork(uuid="part-2", asset_url=self.url),
                self.directory / "2 - Díl.mp3",
                collection=collection,
            )

        self.assertEqual(download.await_count, 2)
        self.assertEqual(
            [call.args[1] for call in download.await_args_list],
            [self.directory / "1 - Díl.jpg", self.directory / "2 - Díl.jpg"],
        )


class TestArtworkPath(unittest.TestCase):
    def test_suffix_comes_from_the_url(self):
        self.assertEqual(
            artwork_path("https://example.com/x/cover.png", Path("/tmp/3 - Díl.mp3")),
            Path("/tmp/3 - Díl.png"),
        )

    def test_defaults_to_jpg(self):
        self.assertEqual(
            artwork_path("https://example.com/asset/42", Path("/tmp/a.mp3")),
            Path("/tmp/a.jpg"),
        )


class TestLibraryOverview(InMemoryLibraryTestCase):
    """What the web grid is built from, without going through HTTP."""

    async def _seed(self, repo: SqliteLibraryRepository) -> None:
        collection = Collection(
            uuid="series-1", type="series", title="Seriál", description="Popis"
        )
        await repo.save_download(
            FakeWork(uuid="a", part=1),
            Path("/tmp/Seriál/1 - Díl.mp3"),
            image_path=Path("/tmp/Seriál/cover.jpg"),
            collection=collection,
        )
        await repo.save_download(
            FakeWork(uuid="b", part=2),
            Path("/tmp/Seriál/2 - Díl.mp3"),
            collection=collection,
        )
        await repo.save_download(FakeWork(uuid="c"), Path("/tmp/Volný.mp3"))

    async def test_works_come_back_with_their_parts_and_artwork(self):
        service = LibraryService(repository=await make_repo())
        await self._seed(service.repository)

        items = await service.overview()

        self.assertEqual([item.title for item in items], ["Seriál", "Místní soubory"])
        series, orphans = items
        self.assertEqual((series.type, series.id), ("series", "series-1"))
        self.assertEqual(series.description, "Popis")
        self.assertEqual(series.count, 2)
        self.assertEqual(series.image_path, "/tmp/Seriál/cover.jpg")
        # Files without a work are listed separately, and last.
        self.assertEqual((orphans.type, orphans.id), ("orphans", "orphans"))
        self.assertEqual(orphans.count, 1)
        self.assertIsNone(orphans.image_path)

    async def test_an_empty_library_shows_nothing(self):
        service = LibraryService(repository=await make_repo())

        self.assertEqual(await service.overview(), [])


class TestLibraryDetail(InMemoryLibraryTestCase):
    """One work with the parts the detail page plays."""

    async def test_a_show_without_part_numbers_lists_the_newest_first(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        collection = Collection(uuid="show-1", type="show", title="Pořad")
        for uuid, since in (
            ("older", "2024-01-01T10:00:00+01:00"),
            ("newer", "2024-03-01T10:00:00+01:00"),
        ):
            await repo.save_download(
                FakeWork(uuid=uuid, part=None, since=since),
                Path(f"/tmp/Pořad/{uuid}.mp3"),
                collection=collection,
            )

        content, episodes = await service.detail("show", "show-1")

        self.assertIsNotNone(content)
        self.assertEqual(content.title, "Pořad")  # type: ignore[union-attr]
        self.assertEqual(content.count, 2)  # type: ignore[union-attr]
        self.assertEqual([episode.uuid for episode in episodes], ["newer", "older"])

    async def test_a_series_is_read_by_part_number(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        collection = Collection(uuid="series-1", type="series", title="Seriál")
        for part in (3, 1, 2):
            await repo.save_download(
                FakeWork(uuid=f"part-{part}", part=part),
                Path(f"/tmp/Seriál/{part} - Díl.mp3"),
                collection=collection,
            )

        _, episodes = await service.detail("series", "series-1")

        self.assertEqual([episode.part for episode in episodes], [1, 2, 3])

    async def test_work_that_is_not_in_the_library_returns_nothing(self):
        service = LibraryService(repository=await make_repo())

        self.assertEqual(await service.detail("series", "nope"), (None, []))
        self.assertEqual(await service.detail("nonsense", "x"), (None, []))

    async def test_orphans_are_the_files_without_a_work(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        await repo.save_download(FakeWork(uuid="a"), Path("/tmp/Volný.mp3"))
        await repo.save_download(
            FakeWork(uuid="b"),
            Path("/tmp/Seriál/1 - Díl.mp3"),
            collection=Collection(uuid="series-1", type="series", title="Seriál"),
        )

        content, episodes = await service.detail("orphans", "orphans")

        self.assertIsNotNone(content)
        self.assertEqual(content.title, "Místní soubory")  # type: ignore[union-attr]
        self.assertEqual([episode.uuid for episode in episodes], ["a"])


if __name__ == "__main__":
    unittest.main()
