import tempfile
import unittest
from datetime import datetime, timezone
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
from crodl.data.attributes import extract_genre
from crodl.library import roots
from crodl.library.scan import LibraryScan
from crodl.library.service import ORPHANS, LibraryService
from crodl.library.refresh import LibraryRefresh, api_id
from crodl.library.tags import read_tags_now, write_tags_now
from crodl.library.updates import (
    AVAILABLE,
    EXPIRED,
    UPCOMING,
    LibraryUpdates,
    part_state,
)
from crodl.program.content import Collection
from mutagen.easyid3 import EasyID3

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
        url: Optional[str] = None,
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
        self.url = url


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


class TestLibraryScanCollections(InMemoryLibraryTestCase):
    """The scan adopts files that are already on disk, one folder per work."""

    def _series_folder(self, download: Path, name: str = "Seriál") -> Path:
        # The literal folder cro-dl writes series into (settings.SERIES_DOWNLOAD_DIR).
        directory = download / "Seriály" / name
        directory.mkdir(parents=True)
        for part in (1, 2):
            (directory / f"{part} - Díl {part}.mp3").write_bytes(b"x")
        return directory

    def _work_folder(self, download: Path, name: str = "Samostatné dílo") -> Path:
        directory = download / name
        directory.mkdir()
        (directory / f"{name}.mp3").write_bytes(b"x")
        return directory

    async def test_a_series_folder_becomes_a_series(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            self._series_folder(download)

            results = await LibraryScan(
                repository=repo, download_path=download
            ).sync_all()

        self.assertEqual(results, {"success": 2, "failed": 0})
        works = await repo.get_all_series()
        self.assertEqual([work.title for work in works], ["Seriál"])
        self.assertEqual(await repo.get_all_shows(), [])
        episodes = await repo.get_episodes_by_series(works[0].uuid)
        self.assertEqual(len(episodes), 2)
        self.assertTrue(all(episode.is_manual for episode in episodes))

    async def test_a_work_folder_becomes_a_show(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            self._work_folder(download)

            await LibraryScan(repository=repo, download_path=download).sync_all()

        works = await repo.get_all_shows()
        self.assertEqual([work.title for work in works], ["Samostatné dílo"])
        self.assertEqual(await repo.get_all_series(), [])
        episodes = await repo.get_episodes_by_show(works[0].uuid)
        self.assertEqual([episode.title for episode in episodes], ["Samostatné dílo"])

    async def test_loose_files_in_the_download_root_stay_orphans(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            (download / "Samostatné dílo.aac").write_bytes(b"x")

            await LibraryScan(repository=repo, download_path=download).sync_all()

        self.assertEqual(await repo.get_all_shows(), [])
        self.assertEqual(await repo.get_all_series(), [])
        self.assertEqual(len(await repo.get_all_episodes()), 1)

    async def test_a_download_already_in_the_library_is_not_filed_twice(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            folder = self._series_folder(download)
            path = folder / "1 - Díl 1.mp3"
            # The same file, already stored under its Czech Radio uuid.
            await repo.save_download(FakeWork(uuid="cro-uuid", title="Díl"), path)

            await LibraryScan(repository=repo, download_path=download).sync_all()

        episodes = await repo.get_all_episodes()
        self.assertEqual(len(episodes), 2)
        stored = await repo.find_episode_by_path(path)
        self.assertEqual(stored.uuid, "cro-uuid")  # type: ignore[union-attr]
        self.assertEqual(stored.title, "Díl")  # type: ignore[union-attr]
        self.assertIsNotNone(stored.series_id)  # type: ignore[union-attr]

    async def test_a_download_that_has_a_work_keeps_it(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            folder = self._series_folder(download)
            path = folder / "1 - Díl 1.mp3"
            await repo.save_download(
                FakeWork(uuid="cro-uuid"), path, series_id="cro-series"
            )

            await LibraryScan(repository=repo, download_path=download).sync_all()

        stored = await repo.find_episode_by_path(path)
        self.assertEqual(stored.series_id, "cro-series")  # type: ignore[union-attr]
        # The folder is adopted as a work of its own for the other part, but
        # the already linked episode must not move into it.
        for work in await repo.get_all_series():
            episodes = await repo.get_episodes_by_series(work.uuid)
            self.assertNotIn("cro-uuid", [episode.uuid for episode in episodes])

    async def test_artwork_next_to_the_files_is_picked_up(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            folder = self._series_folder(download)
            cover = folder / "cover.jpg"
            cover.write_bytes(b"image")
            single = self._work_folder(download)
            own_image = single / "Samostatné dílo.jpg"
            own_image.write_bytes(b"image")

            await LibraryScan(repository=repo, download_path=download).sync_all()

        episodes = {episode.title: episode for episode in await repo.get_all_episodes()}
        self.assertEqual(str(episodes["Díl 1"].image_path), str(cover))
        self.assertEqual(str(episodes["Díl 2"].image_path), str(cover))
        self.assertEqual(str(episodes["Samostatné dílo"].image_path), str(own_image))


class TestLibraryService(InMemoryLibraryTestCase):
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


class TestLibraryMedia(InMemoryLibraryTestCase):
    """What the web layer may hand out: the files the library stored, no more."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.download = Path(self._tmp.name)
        self.folder = self.download / "Seriály" / "Seriál"
        self.folder.mkdir(parents=True)
        self.audio = self.folder / "3 - Díl.mp3"
        self.audio.write_bytes(b"audio")
        self.cover = self.folder / "cover.jpg"
        self.cover.write_bytes(b"image")
        # Things that live in the same directory without being the library's.
        (self.download / "library.db").write_bytes(b"database")
        (self.download / "logs").mkdir()
        (self.download / "logs" / "crodl.log").write_bytes(b"log")

    async def _service(self) -> LibraryService:
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="part-3"),
            self.audio,
            image_path=self.cover,
            collection=Collection(uuid="series-1", type="series", title="Seriál"),
        )
        return LibraryService(repository=repo, download_path=self.download)

    async def test_a_stored_audio_file_is_served(self):
        service = await self._service()

        self.assertEqual(
            await service.media_file("Seriály/Seriál/3 - Díl.mp3"), self.audio
        )

    async def test_the_artwork_of_a_stored_work_is_served(self):
        service = await self._service()

        self.assertEqual(
            await service.media_file("Seriály/Seriál/cover.jpg"), self.cover
        )

    async def test_a_file_the_library_does_not_know_is_not_served(self):
        service = await self._service()

        self.assertIsNone(await service.media_file("library.db"))
        self.assertIsNone(await service.media_file("logs/crodl.log"))

    async def test_a_path_outside_the_download_directory_is_refused(self):
        service = await self._service()

        self.assertIsNone(await service.media_file("../library.db"))
        self.assertIsNone(await service.media_file("Seriály/../../library.db"))
        self.assertIsNone(await service.media_file("/etc/passwd"))

    async def test_a_stored_file_that_is_gone_from_disk_is_not_served(self):
        service = await self._service()
        self.audio.unlink()

        self.assertIsNone(await service.media_file("Seriály/Seriál/3 - Díl.mp3"))


class TestCuration(InMemoryLibraryTestCase):
    """Hand-edited metadata: a work named after its folder gets a real name."""

    async def _service(self) -> tuple[LibraryService, SqliteLibraryRepository]:
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="part-1"),
            Path("/tmp/Seriály/Složka/1 - Díl.mp3"),
            collection=Collection(uuid="series-1", type="series", title="Složka"),
        )
        return LibraryService(repository=repo), repo

    async def test_a_work_gets_the_name_a_person_gave_it(self):
        service, repo = await self._service()

        renamed = await service.curate_work(
            "series",
            "series-1",
            {"title": "Bohumil Hrabal: Obsluhoval jsem anglického krále"},
        )

        self.assertTrue(renamed)
        row = await repo.get_series("series-1")
        self.assertEqual(
            row.title,  # type: ignore[union-attr]
            "Bohumil Hrabal: Obsluhoval jsem anglického krále",
        )

    async def test_a_blank_title_leaves_the_work_alone(self):
        service, repo = await self._service()

        handled = await service.curate_work(
            "series", "series-1", {"title": "   ", "description": "Popis"}
        )

        self.assertTrue(handled)
        row = await repo.get_series("series-1")
        self.assertEqual(row.title, "Složka")  # type: ignore[union-attr]
        self.assertEqual(row.description, "Popis")  # type: ignore[union-attr]

    async def test_a_form_without_changes_is_still_a_known_work(self):
        # The UI posts every field; "nothing changed" must not read as "no such
        # work" (which the route answers with a 404).
        service, _ = await self._service()

        self.assertTrue(await service.curate_work("series", "series-1", {}))

    async def test_a_blank_description_clears_it(self):
        service, repo = await self._service()
        await service.curate_work(
            "series", "series-1", {"title": "Název", "description": "Popis"}
        )

        await service.curate_work(
            "series", "series-1", {"title": "Název", "description": "   "}
        )

        row = await repo.get_series("series-1")
        self.assertIsNone(row.description)  # type: ignore[union-attr]

    async def test_the_grid_shows_the_new_name(self):
        service, _ = await self._service()

        await service.curate_work("series", "series-1", {"title": "Přejmenovaný"})
        items = await service.overview()

        self.assertEqual([item.title for item in items], ["Přejmenovaný"])

    async def test_an_unknown_work_is_not_curated(self):
        service, _ = await self._service()

        self.assertFalse(await service.curate_work("series", "nope", {"title": "X"}))
        self.assertFalse(
            await service.curate_work("nonsense", "series-1", {"title": "X"})
        )

    async def test_a_part_of_a_work_can_be_edited_too(self):
        service, repo = await self._service()

        edited = await service.curate_part(
            "part-1",
            {
                "title": "Díl první",
                "author": "Bohumil Hrabal",
                "description": "Popis dílu",
            },
        )

        self.assertTrue(edited)
        row = await repo.get_episode("part-1")
        self.assertEqual(row.title, "Díl první")  # type: ignore[union-attr]
        self.assertEqual(row.author, "Bohumil Hrabal")  # type: ignore[union-attr]
        self.assertEqual(row.description, "Popis dílu")  # type: ignore[union-attr]

    async def test_editing_keeps_the_rest_of_the_row(self):
        # `save_download()` would blank these: it builds a whole row and merge()
        # writes every column, which is why curation updates in place.
        service, repo = await self._service()

        await service.curate_part("part-1", {"title": "Díl první"})

        row = await repo.get_episode("part-1")
        self.assertEqual(row.local_path, "/tmp/Seriály/Složka/1 - Díl.mp3")  # type: ignore[union-attr]
        self.assertEqual(row.series_id, "series-1")  # type: ignore[union-attr]
        self.assertEqual(row.meta["variants"], ["mp3", "hls"])  # type: ignore[union-attr]

    async def test_only_curated_columns_may_be_written(self):
        _, repo = await self._service()

        with self.assertRaises(ValueError):
            await repo.update_episode("part-1", {"local_path": "/tmp/elsewhere.mp3"})

    async def test_editing_an_unknown_part_reports_nothing_happened(self):
        service, _ = await self._service()

        self.assertFalse(await service.curate_part("nope", {"title": "Díl"}))


class TestForgetting(InMemoryLibraryTestCase):
    """Deleting a record from the library - the files stay on disk."""

    async def _seed(self, repo: SqliteLibraryRepository) -> Path:
        audio = Path("/tmp/Seriály/Seriál/1 - Díl.mp3")
        await repo.save_download(
            FakeWork(uuid="part-1"),
            audio,
            collection=Collection(uuid="series-1", type="series", title="Seriál"),
        )
        await repo.save_download(FakeWork(uuid="part-2"), Path("/tmp/Volný.mp3"))
        return audio

    async def test_a_work_leaves_the_library_with_its_parts(self):
        repo = await make_repo()
        await self._seed(repo)
        service = LibraryService(repository=repo)

        removed = await service.forget("series", "series-1")

        self.assertEqual(removed, 2)  # the work and its one part
        self.assertIsNone(await repo.get_series("series-1"))
        self.assertEqual(
            [episode.uuid for episode in await repo.get_all_episodes()], ["part-2"]
        )

    async def test_the_other_works_are_left_alone(self):
        repo = await make_repo()
        await self._seed(repo)
        await repo.save_download(
            FakeWork(uuid="other"),
            Path("/tmp/Jiný/1 - Díl.mp3"),
            collection=Collection(uuid="series-2", type="series", title="Jiný"),
        )
        service = LibraryService(repository=repo)

        await service.forget("series", "series-1")

        self.assertEqual(
            [e.uuid for e in await repo.get_episodes_by_series("series-2")], ["other"]
        )

    async def test_the_files_on_disk_are_not_touched(self):
        repo = await make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "1 - Díl.mp3"
            audio.write_bytes(b"audio")
            await repo.save_download(
                FakeWork(uuid="part-1"),
                audio,
                collection=Collection(uuid="series-1", type="series", title="Seriál"),
            )
            service = LibraryService(repository=repo)

            await service.forget("series", "series-1")

            self.assertTrue(audio.exists())

    async def test_the_files_without_a_work_can_be_removed(self):
        repo = await make_repo()
        await self._seed(repo)
        service = LibraryService(repository=repo)

        removed = await service.forget("orphans", "orphans")

        self.assertEqual(removed, 1)
        self.assertEqual([e.uuid for e in await repo.get_all_episodes()], ["part-1"])

    async def test_an_unknown_work_removes_nothing(self):
        repo = await make_repo()
        await self._seed(repo)
        service = LibraryService(repository=repo)

        self.assertEqual(await service.forget("series", "nope"), 0)
        self.assertEqual(await service.forget("nonsense", "nope"), 0)
        self.assertEqual(len(await repo.get_all_episodes()), 2)


class FakeApi:
    """Stands in for `CroAPIClient`: hands out the attributes a test set up."""

    def __init__(
        self,
        work: dict | None = None,
        episode: dict | None = None,
        episodes: list[dict] | None = None,
        genres: list[str] | None = None,
        episode_relationships: dict | None = None,
    ) -> None:
        self.work = work or {}
        self.episode = episode or {}
        self.episodes = episodes or []
        self.genres = genres or []
        self.episode_relationships = episode_relationships or {}
        self.calls: list[tuple[str, str]] = []

    def _record(self) -> dict:
        """A work record: its attributes, plus the genres beside them."""
        return {"data": {"attributes": self.work, "relationships": self._genres()}}

    def _genres(self) -> dict:
        """The genres relationship, when the test set any."""
        if not self.genres:
            return dict(self.episode_relationships)

        relationships = dict(self.episode_relationships)
        relationships["genres"] = {
            "data": [{"attributes": {"title": genre}} for genre in self.genres]
        }

        return relationships

    def get_series_data(self, uuid: str) -> dict:
        self.calls.append(("series", uuid))
        return self._record()

    def get_show_data(self, uuid: str) -> dict:
        self.calls.append(("show", uuid))
        return self._record()

    def get_episode_data(self, uuid: str) -> dict:
        self.calls.append(("episode", uuid))
        return {
            "data": {
                "attributes": self.episode,
                "relationships": self._genres(),
            }
        }

    def get_related_data(self, url: str) -> dict:
        self.calls.append(("episodes", url))
        return {"data": self.episodes}

    def get_series_id(self, url: str) -> Optional[str]:
        self.calls.append(("series_id", url))
        return None

    def get_show_uuid(self, url: str) -> Optional[str]:
        self.calls.append(("show_uuid", url))
        return None


class TestApiId(unittest.TestCase):
    """A work adopted from disk is keyed by a hash the API has never heard of."""

    def test_a_czech_radio_uuid(self):
        self.assertTrue(api_id("9d0f0f0e-1111-2222-3333-444455556666"))

    def test_a_scan_hash_and_nothing(self):
        self.assertFalse(api_id("47668695b67d4acd"))
        self.assertFalse(api_id(""))
        self.assertFalse(api_id(None))


class TestRefresh(InMemoryLibraryTestCase):
    """Filling in what the library is missing, from the content API."""

    uuid = "9d0f0f0e-1111-2222-3333-444455556666"
    part_uuid = "aaaa0001-1111-2222-3333-444455556666"

    async def _library(
        self, download: Path, api: FakeApi, *, with_image: bool = False
    ) -> tuple[LibraryService, SqliteLibraryRepository]:
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid=self.part_uuid, author=None, description=None, duration=None),
            download / "1 - Díl.mp3",
            image_path=download / "own.jpg" if with_image else None,
            collection=Collection(uuid=self.uuid, type="series", title="Složka"),
        )
        service = LibraryService(
            repository=repo,
            download_path=download,
            refresher=LibraryRefresh(repository=repo, client=api),
        )

        return service, repo

    async def test_it_fills_what_the_records_have_never_had(self):
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            api = FakeApi(
                work={"title": "Skutečný název", "description": "<p>Popis seriálu</p>"},
                episode={
                    "author": "Bohumil Hrabal",
                    "description": "Popis dílu",
                    "duration": 1800,
                },
            )
            service, repo = await self._library(download, api)

            filled = await service.refresh("series", self.uuid)

        self.assertIsNotNone(filled)
        self.assertEqual(filled.images, 0)  # type: ignore[union-attr]
        work = await repo.get_series(self.uuid)
        # The name somebody chose stays; only the empty description is filled in.
        self.assertEqual(work.title, "Složka")  # type: ignore[union-attr]
        self.assertEqual(work.description, "Popis seriálu")  # type: ignore[union-attr]
        episode = await repo.get_episode(self.part_uuid)
        self.assertEqual(episode.author, "Bohumil Hrabal")  # type: ignore[union-attr]
        self.assertEqual(episode.description, "Popis dílu")  # type: ignore[union-attr]
        self.assertEqual(episode.duration, 1800)  # type: ignore[union-attr]

    async def test_the_work_cover_reaches_the_parts_that_have_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            cover = download / "cover.jpg"
            cover.write_bytes(b"image")
            api = FakeApi(
                work={"asset": {"url": "https://example.com/cover.jpg"}},
                episode={},
            )
            service, repo = await self._library(download, api)

            with mock.patch(
                "crodl.library.refresh.fetch_cover",
                new=mock.AsyncMock(return_value=cover),
            ) as fetch:
                filled = await service.refresh("series", self.uuid)

        self.assertEqual(filled.images, 1)  # type: ignore[union-attr]
        fetch.assert_not_awaited()  # the file was already there: no download
        episode = await repo.get_episode(self.part_uuid)
        self.assertEqual(episode.image_path, str(cover))  # type: ignore[union-attr]

    async def test_a_part_that_has_artwork_keeps_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            download = Path(tmp)
            api = FakeApi(work={"asset": {"url": "https://example.com/cover.jpg"}})
            service, repo = await self._library(download, api, with_image=True)

            filled = await service.refresh("series", self.uuid)

        self.assertEqual(filled.images, 0)  # type: ignore[union-attr]

    async def test_nothing_to_ask_about(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeApi()
            service, _ = await self._library(Path(tmp), api)

            # A hash is not a Czech Radio uuid.
            self.assertIsNone(await service.refresh("series", "47668695b67d4acd"))
            # The files without a work are asked part by part (their own records
            # name the works they aired in), so this one answers - with nothing
            # found here, since none of them is in the API.
            loose = await service.refresh("orphans", "orphans")
            self.assertEqual((loose.fields, loose.images), (0, 0))  # type: ignore[union-attr]

        self.assertEqual(api.calls, [])

    async def test_an_api_that_is_away_does_not_break_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeApi()
            api.get_series_data = mock.Mock(side_effect=OSError("no network"))  # type: ignore[method-assign]
            service, _ = await self._library(Path(tmp), api)

            # An API that is away must not break the page: the work still takes
            # whatever lies next to its files (nothing, here).
            filled = await service.refresh("series", self.uuid)
            self.assertEqual((filled.fields, filled.images), (0, 0))  # type: ignore[union-attr]


class TestNewParts(InMemoryLibraryTestCase):
    """Watching a series for parts the Czech Radio has released since."""

    uuid = "9d0f0f0e-1111-2222-3333-444455556666"
    stored = "aaaa0001-1111-2222-3333-444455556666"

    def _api(self, parts: int = 3, *, state: str = AVAILABLE) -> FakeApi:
        """Episodes as the API reports them, in the given availability."""
        availability = {
            AVAILABLE: {
                "since": "2024-01-01T10:00:00+01:00",
                "audioLinks": [{"variant": "mp3", "url": "u.mp3"}],
            },
            UPCOMING: {"since": "2999-01-01T10:00:00+01:00", "audioLinks": []},
            EXPIRED: {"since": "2024-01-01T10:00:00+01:00", "audioLinks": []},
        }[state]

        return FakeApi(
            episodes=[
                {
                    "id": f"aaaa{number:04d}-1111-2222-3333-444455556666",
                    "attributes": {
                        "title": f"Díl {number}",
                        "part": number,
                        "asset": {"url": "https://example.com/cover.jpg"},
                        **availability,
                    },
                }
                for number in range(1, parts + 1)
            ]
        )

    async def _library(
        self, repo: SqliteLibraryRepository, api: FakeApi
    ) -> LibraryService:
        return LibraryService(
            repository=repo,
            updates=LibraryUpdates(repository=repo, client=api),
        )

    async def _store_one_part(self, repo: SqliteLibraryRepository) -> None:
        await repo.save_download(
            FakeWork(uuid=self.stored),
            Path("/tmp/Seriály/Složka/1 - Díl.mp3"),
            collection=Collection(uuid=self.uuid, type="series", title="Složka"),
        )

    async def test_it_finds_the_parts_the_library_does_not_have(self):
        repo = await make_repo()
        await self._store_one_part(repo)
        service = await self._library(repo, self._api(parts=3))

        missing = await service.missing_parts("series", self.uuid)

        self.assertIsNotNone(missing)
        self.assertEqual([part.part for part in missing or []], [2, 3])
        self.assertEqual((missing or [])[0].title, "Díl 2")
        # The image travels along, so the parts can share the work's cover.
        self.assertEqual((missing or [])[0].asset_url, "https://example.com/cover.jpg")
        self.assertTrue(all(part.fetchable for part in missing or []))

    async def test_a_part_whose_stream_expired_is_not_news(self):
        # The reported bug: two parts the API still lists, with no streams left,
        # were announced as "2 nové díly".
        repo = await make_repo()
        await self._store_one_part(repo)
        service = await self._library(repo, self._api(parts=3, state=EXPIRED))

        missing = await service.missing_parts("series", self.uuid)
        check = await service.check_work("series", self.uuid)

        self.assertEqual([part.state for part in missing or []], [EXPIRED, EXPIRED])
        self.assertFalse(any(part.fetchable for part in missing or []))
        self.assertEqual((check.available, check.expired), (0, 2))  # type: ignore[union-attr]

    async def test_a_part_that_has_not_aired_yet(self):
        repo = await make_repo()
        await self._store_one_part(repo)
        service = await self._library(repo, self._api(parts=3, state=UPCOMING))

        check = await service.check_work("series", self.uuid)

        self.assertEqual((check.available, check.upcoming), (0, 2))  # type: ignore[union-attr]

    async def test_a_work_the_api_cannot_know_is_left_alone(self):
        repo = await make_repo()
        service = await self._library(repo, self._api())

        self.assertIsNone(await service.missing_parts("series", "47668695b67d4acd"))
        self.assertIsNone(await service.missing_parts("orphans", "orphans"))

    async def test_the_finding_is_remembered_for_the_grid(self):
        repo = await make_repo()
        await self._store_one_part(repo)
        service = await self._library(repo, self._api(parts=3))

        await service.check_for_new_parts()
        items = await service.overview()

        watched = [item for item in items if item.id == self.uuid][0]
        self.assertEqual(watched.available, 2)
        self.assertIsNotNone(watched.checked_at)

    async def test_a_complete_work_reports_nothing_new(self):
        repo = await make_repo()
        await self._store_one_part(repo)
        service = await self._library(repo, self._api(parts=1))

        self.assertEqual(await service.check_for_new_parts(), 0)
        watched = [item for item in await service.overview() if item.id == self.uuid][0]
        self.assertEqual(watched.available, 0)

    async def test_an_api_that_is_away_is_reported_as_nothing_new(self):
        repo = await make_repo()
        await self._store_one_part(repo)
        api = self._api(parts=3)
        api.get_related_data = mock.Mock(side_effect=OSError("no network"))  # type: ignore[method-assign]
        service = await self._library(repo, api)

        self.assertIsNone(await service.missing_parts("series", self.uuid))
        self.assertEqual(await service.check_for_new_parts(), 0)


class TestPartState(unittest.TestCase):
    """What a part the library lacks actually is (the reported bug)."""

    now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    links = [{"variant": "hls", "url": "u.m3u8"}]

    def test_a_part_that_is_there_to_fetch(self):
        self.assertEqual(
            part_state(
                {"since": "2026-10-01T18:30:00+02:00", "audioLinks": self.links},
                self.now,
            ),
            AVAILABLE,
        )

    def test_a_part_the_radio_has_not_aired_yet(self):
        self.assertEqual(
            part_state(
                {"since": "2026-11-01T18:30:00+02:00", "audioLinks": self.links},
                self.now,
            ),
            UPCOMING,
        )

    def test_a_part_whose_stream_is_gone(self):
        self.assertEqual(
            part_state(
                {"since": "2026-09-01T18:30:00+02:00", "audioLinks": []}, self.now
            ),
            EXPIRED,
        )

    def test_an_old_broadcast_end_does_not_make_a_part_gone(self):
        # The Kondora case: parts 4-15 carry a `till` weeks in the past while
        # their streams are alive; `till` is the broadcast, not the stream.
        self.assertEqual(
            part_state(
                {
                    "since": "2026-08-12T18:30:00+02:00",
                    "till": "2026-08-12T19:30:00+02:00",
                    "audioLinks": self.links,
                },
                self.now,
            ),
            AVAILABLE,
        )


class TestSourceUrl(InMemoryLibraryTestCase):
    """A work adopted from disk can be told which page it came from."""

    link = "https://www.mujrozhlas.cz/cetba-na-pokracovani/kondor"
    resolved = "9d0f0f0e-1111-2222-3333-444455556666"

    async def _library(self, repo: SqliteLibraryRepository, api=None) -> LibraryService:
        await repo.save_download(
            FakeWork(uuid="aaaa0001-1111-2222-3333-444455556666"),
            Path("/tmp/Seriály/Složka/1 - Díl.mp3"),
            collection=Collection(uuid="hash-1", type="series", title="Složka"),
        )
        return LibraryService(
            repository=repo,
            refresher=LibraryRefresh(repository=repo, client=api or FakeApi()),
        )

    async def test_a_page_link_is_stored(self):
        service = await self._library(await make_repo())

        stored = await service.set_source_url("series", "hash-1", self.link)

        self.assertIsNotNone(stored)
        self.assertEqual(await service.source_url("hash-1"), self.link)

    async def test_a_foreign_or_empty_link_is_refused(self):
        service = await self._library(await make_repo())

        self.assertIsNone(
            await service.set_source_url("series", "hash-1", "https://example.com/x")
        )
        self.assertIsNone(await service.set_source_url("series", "hash-1", "   "))
        self.assertIsNone(await service.source_url("hash-1"))

    async def test_the_uuid_is_read_from_the_link_and_remembered(self):
        repo = await make_repo()
        api = FakeApi(work={"description": "<p>Popis seriálu</p>"})
        api.get_series_id = mock.Mock(return_value=self.resolved)  # type: ignore[method-assign]
        service = await self._library(repo, api)
        await service.set_source_url("series", "hash-1", self.link)

        filled = await service.refresh("series", "hash-1")

        self.assertEqual(filled.fields, 1)  # type: ignore[union-attr]  the description
        link = await repo.get_work_link("hash-1")
        self.assertEqual(link.resolved_uuid, self.resolved)  # type: ignore[union-attr]

    async def test_a_work_without_a_link_and_without_a_uuid_asks_nothing(self):
        repo = await make_repo()
        service = await self._library(repo)

        # Nothing to ask the API about, but an image next to the files is still
        # worth taking - there is none here, so the answer is "nothing".
        filled = await service.refresh("series", "hash-1")
        self.assertEqual((filled.fields, filled.images), (0, 0))  # type: ignore[union-attr]


class TestTags(unittest.TestCase):
    """What the library knows about a work belongs in the file itself."""

    def test_the_tags_are_written_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "3 - Díl.mp3"
            path.write_bytes(b"")

            written = write_tags_now(
                path,
                title="Díl",
                author="Bohumil Hrabal",
                album="Seriál",
                genre="Horor",
                track=3,
            )

            self.assertTrue(written)
            tags = EasyID3(str(path))
            self.assertEqual(tags["title"], ["Díl"])
            self.assertEqual(tags["artist"], ["Bohumil Hrabal"])
            self.assertEqual(tags["album"], ["Seriál"])
            self.assertEqual(tags["genre"], ["Horor"])
            self.assertEqual(tags["tracknumber"], ["3"])

    def test_a_raw_aac_file_takes_an_id3_tag_too(self):
        # Czech Radio streams come down as ADTS .aac, with no container to tag.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "9 - Díl.aac"
            path.write_bytes(b"")

            self.assertTrue(write_tags_now(path, title="Devátý", track=9))
            self.assertEqual(read_tags_now(path)["title"], "Devátý")

    def test_nothing_to_write_or_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.mp3"
            path.write_bytes(b"")

            self.assertFalse(write_tags_now(path))  # nothing known
            self.assertFalse(write_tags_now(Path(tmp) / "gone.mp3", title="Díl"))

    def test_a_file_it_cannot_tag_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("x", encoding="utf-8")

            self.assertFalse(write_tags_now(path, title="Díl"))
            self.assertEqual(path.read_text(encoding="utf-8"), "x")

    def test_the_genre_comes_from_the_api_payload(self):
        payload = {
            "data": {
                "relationships": {
                    "genres": {"data": [{"attributes": {"title": "Horor"}}]}
                }
            }
        }

        self.assertEqual(extract_genre(payload), "Horor")
        self.assertIsNone(extract_genre({}))
        self.assertIsNone(extract_genre({"data": {"relationships": {}}}))


class TestWorkTags(InMemoryLibraryTestCase):
    """Edit mode writes the library's knowledge into the files themselves."""

    uuid = "aaaa0000-1111-2222-3333-444455556666"

    async def _library_with_parts(self, tmp: str) -> tuple[LibraryService, Path]:
        repo = await make_repo()
        collection = Collection(
            uuid=self.uuid, type="series", title="Seriál", genre="Horor"
        )
        folder = Path(tmp)

        for part in (1, 2):
            path = folder / f"{part} - Díl.mp3"
            path.write_bytes(b"")
            await repo.save_download(
                FakeWork(
                    uuid=f"aaaa000{part}-1111-2222-3333-444455556666",
                    title=f"{part}-Díl",
                    part=part,
                ),
                path,
                audio_format="mp3",
                collection=collection,
            )

        return LibraryService(repository=repo), folder

    async def test_every_part_gets_the_works_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, folder = await self._library_with_parts(tmp)

            written = await service.write_work_tags("series", self.uuid)

            self.assertEqual(written, 2)
            tags = read_tags_now(folder / "2 - Díl.mp3")
            self.assertEqual(tags["title"], "2-Díl")
            self.assertEqual(tags["album"], "Seriál")
            self.assertEqual(tags["genre"], "Horor")  # the work's genre, item 1
            self.assertEqual(tags["tracknumber"], "2")

    async def test_a_work_that_is_not_there_writes_nothing(self):
        service = LibraryService(repository=await make_repo())

        self.assertEqual(await service.write_work_tags("series", "nope"), 0)


class TestAnEpisodeBehindAShow(InMemoryLibraryTestCase):
    """The reported bug: the page's uuid is an episode, the work is stored as a show."""

    uuid = "063a6a5f-c5f2-39ec-b085-34cb85d46230"  # what that page really answers
    link = (
        "https://www.mujrozhlas.cz/sobotni-drama/"
        "pavel-landovsky-hodinovy-hotelier-hrusinsky-lukavsky-ve-hre-o-destrukci-lidskych"
    )
    episode = {
        "title": "Pavel Landovský: Hodinový hoteliér",
        "description": "<p>Hra o destrukci lidských vztahů.</p>",
    }

    async def test_the_episode_fills_the_show_row(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="aaaa0001-1111-2222-3333-444455556666", title="1-Složka"),
            Path("/tmp/Z Rozhlasu/Složka/1 - Díl.mp3"),
            collection=Collection(uuid="hash-1", type="show", title="Složka"),
        )
        api = FakeApi(episode=self.episode)
        # The page answers with an episode uuid, as the real one does.
        api.get_series_id = mock.Mock(return_value=self.uuid)  # type: ignore[method-assign]
        service = LibraryService(
            repository=repo,
            refresher=LibraryRefresh(repository=repo, client=api),
        )
        await service.set_source_url("show", "hash-1", self.link)

        filled = await service.refresh("show", "hash-1")

        # The row is a show, but the record behind it is an episode: the API is
        # asked until one of its kinds answers.
        self.assertIn(("episode", self.uuid), api.calls)
        self.assertEqual(filled.fields, 1)  # type: ignore[union-attr]
        show = await repo.get_show("hash-1")
        self.assertIn("destrukci", show.description or "")  # type: ignore[union-attr]


class TestGenres(InMemoryLibraryTestCase):
    """The genre of a whole work: edited by hand, written into its parts' tags."""

    uuid = "aaaa0000-1111-2222-3333-444455556666"
    genre = "Pohádka"

    async def _library(self, repo: SqliteLibraryRepository) -> LibraryService:
        await repo.save_download(
            FakeWork(uuid="aaaa0001-1111-2222-3333-444455556666", title="1-Díl"),
            Path("/tmp/Z Rozhlasu/Seriály/S/1 - Díl.mp3"),
            collection=Collection(
                uuid=self.uuid, type="series", title="Seriál", genre=self.genre
            ),
        )

        return LibraryService(repository=repo)

    async def test_a_download_brings_the_genre_along(self):
        service = await self._library(await make_repo())

        item = [i for i in await service.overview() if i.id == self.uuid][0]

        self.assertEqual(item.genre, self.genre)
        self.assertEqual(await service.genres(), [self.genre])

    async def test_the_genre_can_be_edited_and_cleared(self):
        repo = await make_repo()
        service = await self._library(repo)

        self.assertTrue(
            await service.curate_work("series", self.uuid, {"genre": "Horor"})
        )
        detail = await service.detail("series", self.uuid)
        self.assertEqual(detail[0].genre, "Horor")  # type: ignore[union-attr]

        self.assertTrue(await service.curate_work("series", self.uuid, {"genre": ""}))
        detail = await service.detail("series", self.uuid)
        self.assertIsNone(detail[0].genre)  # type: ignore[union-attr]

    async def test_a_refresh_takes_the_genres_from_the_api(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="aaaa0001-1111-2222-3333-444455556666", title="1-Díl"),
            Path("/tmp/Z Rozhlasu/Seriály/S/1 - Díl.mp3"),
            collection=Collection(uuid=self.uuid, type="series", title="Seriál"),
        )
        api = FakeApi(work={"title": "Podle API"}, genres=["Krimi", "Thriller"])
        service = LibraryService(
            repository=repo, refresher=LibraryRefresh(repository=repo, client=api)
        )

        await service.refresh("series", self.uuid)

        self.assertEqual((await service.detail("series", self.uuid))[0].genre, "Krimi")

    async def test_an_edited_genre_is_not_overwritten_by_a_download(self):
        repo = await make_repo()
        service = await self._library(repo)
        await service.curate_work("series", self.uuid, {"genre": "Horor"})

        # The same work arrives again (another part), genre and all.
        await repo.save_download(
            FakeWork(uuid="aaaa0002-1111-2222-3333-444455556666", title="2-Díl"),
            Path("/tmp/Z Rozhlasu/Seriály/S/2 - Díl.mp3"),
            collection=Collection(
                uuid=self.uuid, type="series", title="Seriál", genre="Pohádka"
            ),
        )

        self.assertEqual((await service.detail("series", self.uuid))[0].genre, "Horor")


class TestLibraryRoots(InMemoryLibraryTestCase):
    """A folder of audio added by hand: registered, imported, forgotten."""

    async def test_a_folder_that_is_not_there_is_refused(self):
        service = LibraryService(repository=await make_repo())

        self.assertIsNone(await service.add_root("/nonexistent/nope"))
        self.assertIsNone(await service.add_root(""))
        self.assertEqual(await service.stored_roots(), [])

    async def test_an_added_folder_is_imported_and_served(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Sbírka"
            (root / "Dílo").mkdir(parents=True)
            (root / "Dílo" / "1 - Část.mp3").write_bytes(b"")
            (root / "Dílo" / "2 - Část.mp3").write_bytes(b"")

            added = await service.add_root(str(root))
            self.assertIsNotNone(added)

            try:
                imported = await service.import_root(added.path)  # type: ignore[union-attr]
                self.assertEqual(imported["success"], 2)

                works = [i for i in await service.overview() if i.title == "Dílo"]
                self.assertEqual(len(works), 1)
                self.assertEqual(works[0].count, 2)

                # The files are served through the added folder, as anywhere else.
                self.assertIn(root, service.known_roots())
                served = await service.media_file("Dílo/1 - Část.mp3")
                self.assertEqual(served, root / "Dílo" / "1 - Část.mp3")
            finally:
                self.assertTrue(
                    await service.forget_root(added.path)  # type: ignore[union-attr]
                )

            self.assertNotIn(root, service.known_roots())
            self.assertEqual(await service.stored_roots(), [])

    async def test_an_unavailable_folder_is_reported(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)
        away = Path("/nonexistent/odpojeny-disk")
        await service.add_root("/tmp")  # hmm: a folder that is there

        roots.register(away)

        try:
            self.assertIn(away, service.missing_roots())
        finally:
            roots.forget(away)
            roots.forget(Path("/tmp"))


class TestAOneOffEpisode(InMemoryLibraryTestCase):
    """A play aired in a show is a work of its own, named after the play."""

    # The real ids from the reported page.
    show_uuid = "0e65e92d-3eb9-329a-8b35-86d9b7e1ce76"
    episode_uuid = "6be024ac-b862-3d3e-afea-4f21d73b3e8e"
    title = "Kateřina Surmanová: Zvedá se vítr"
    page = (
        "https://www.mujrozhlas.cz/hra-na-nedeli/"
        "katerina-surmanova-zveda-se-vitr-premiera-krimi-mystery-z-moravy-misici-fikci"
    )
    path = Path("/tmp/Z Rozhlasu/Kateřina Surmanová - Zvedá se vítr/Zvedá se vítr.aac")

    async def test_the_episode_becomes_a_work_of_its_own(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)

        await service.save_download(
            FakeWork(
                uuid=self.episode_uuid,
                title=self.title,
                part=None,
                url=self.page,
            ),
            self.path,
            audio_format="aac",
        )

        items = await service.overview()
        works = [item for item in items if item.title == self.title]
        self.assertEqual(len(works), 1)
        # The work is keyed by the part's uuid, which is what the API knows.
        self.assertEqual(works[0].id, self.episode_uuid)
        self.assertEqual(works[0].count, 1)
        self.assertEqual([item for item in items if item.type == ORPHANS], [])

        episode = await repo.find_episode_by_path(self.path)
        self.assertEqual(episode.show_id, self.episode_uuid)  # type: ignore[union-attr]
        # Where it came from is stored, with the work and on the part itself.
        self.assertEqual(episode.source_url, self.page)  # type: ignore[union-attr]
        self.assertEqual(await service.source_url(self.episode_uuid), self.page)

    async def test_a_file_without_an_api_uuid_stays_loose(self):
        repo = await make_repo()
        service = LibraryService(repository=repo)

        await service.save_download(
            FakeWork(uuid="hash-of-a-file", title="Samostatné", part=None),
            Path("/tmp/Z Rozhlasu/Samostatné.aac"),
            audio_format="aac",
        )

        items = await service.overview()
        self.assertEqual([item.type for item in items], [ORPHANS])

    async def test_a_loose_part_gets_its_own_work_when_the_library_asks(self):
        repo = await make_repo()
        # A part stored before cro-dl made works of such downloads.
        await repo.save_download(
            FakeWork(uuid=self.episode_uuid, title="Zvedá se vítr", part=None),
            self.path,
            audio_format="aac",
        )
        api = FakeApi(
            episode={
                "title": self.title,
                "description": "<p>Krimi mystery z Moravy.</p>",
            },
            genres=["Krimi"],
        )
        service = LibraryService(
            repository=repo, refresher=LibraryRefresh(repository=repo, client=api)
        )

        linked = await service.link_loose_parts()

        self.assertEqual(linked, 1)
        works = [
            item for item in await service.overview() if item.id == self.episode_uuid
        ]
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].genre, "Krimi")  # the part's own genre, from the API
        episode = await repo.find_episode_by_path(self.path)
        self.assertEqual(episode.show_id, self.episode_uuid)  # type: ignore[union-attr]

    async def test_a_file_the_api_does_not_know_is_left_alone(self):
        repo = await make_repo()
        # A file the scan adopted: keyed by a hash the API has never heard of.
        await repo.save_download(
            FakeWork(uuid="hash-of-a-folder", title="Z ulice", part=None),
            Path("/tmp/Z Rozhlasu/Z ulice/Z ulice.aac"),
            audio_format="aac",
        )
        service = LibraryService(repository=repo)

        self.assertEqual(await service.link_loose_parts(), 0)


class TestCheckSurvivesABadWork(InMemoryLibraryTestCase):
    """A work the database refuses must not stop the check (the reported crash)."""

    uuid = "aaaa0000-1111-2222-3333-444455556666"

    async def test_the_check_carries_on_without_the_broken_one(self):
        repo = await make_repo()
        await repo.save_download(
            FakeWork(uuid="aaaa0001-1111-2222-3333-444455556666", title="1-Díl"),
            Path("/tmp/Z Rozhlasu/Seriály/S/1 - Díl.mp3"),
            collection=Collection(uuid=self.uuid, type="series", title="Seriál"),
        )

        async def refuse(check: object) -> None:
            raise ValueError("NOT NULL constraint failed: updatecheck.missing")

        repo.save_update_check = refuse  # what an old library.db used to do

        checked = await LibraryUpdates(
            repository=repo, client=FakeApi(episodes=[])
        ).check_all()

        self.assertEqual(checked, 0)  # nothing counted, and nothing raised


class TestArtworkFromDisk(InMemoryLibraryTestCase):
    """An image lying next to the audio becomes the cover of the work."""

    image = b"\x89PNG\r\n\x1a\n not really an image"
    episode_uuid = "aaaa0001-1111-2222-3333-444455556666"

    async def _work_over_files(
        self,
        tmp: str,
        *,
        image_path: Optional[Path] = None,
        uuid: str = "hash-1",
    ) -> tuple[SqliteLibraryRepository, Path]:
        repo = await make_repo()
        folder = Path(tmp)
        (folder / "1 - Díl.mp3").write_bytes(b"")
        await repo.save_download(
            FakeWork(uuid=self.episode_uuid, title="1-Díl"),
            folder / "1 - Díl.mp3",
            audio_format="mp3",
            image_path=image_path,
            collection=Collection(uuid=uuid, type="series", title="Složka"),
        )

        return repo, folder

    async def test_a_cover_in_the_folder_is_taken_when_the_api_knows_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, folder = await self._work_over_files(tmp)
            (folder / "cover.jpg").write_bytes(self.image)
            service = LibraryService(repository=repo)

            filled = await service.refresh("series", "hash-1")

            self.assertEqual(filled.images, 1)  # type: ignore[union-attr]
            episode = await repo.find_episode_by_path(folder / "1 - Díl.mp3")
            self.assertEqual(episode.image_path, str(folder / "cover.jpg"))  # type: ignore[union-attr]
            # And the grid shows it.
            items = await service.overview()
            self.assertEqual(items[0].image_path, str(folder / "cover.jpg"))

    async def test_a_cover_in_the_folder_is_taken_when_the_api_has_no_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            uuid = "aaaa0000-1111-2222-3333-444455556666"
            repo, folder = await self._work_over_files(tmp, uuid=uuid)
            (folder / "cover.jpg").write_bytes(self.image)
            api = FakeApi(work={"title": "Složka"})  # the API reports no image
            service = LibraryService(
                repository=repo, refresher=LibraryRefresh(repository=repo, client=api)
            )

            filled = await service.refresh("series", uuid)

            self.assertEqual(filled.images, 1)  # type: ignore[union-attr]

    async def test_a_part_whose_image_is_gone_gets_the_folder_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            repo, folder = await self._work_over_files(
                tmp, image_path=folder / "gone.jpg"
            )
            (folder / "cover.jpg").write_bytes(self.image)
            service = LibraryService(repository=repo)

            filled = await service.refresh("series", "hash-1")

            self.assertEqual(filled.images, 1)  # type: ignore[union-attr]
            episode = await repo.find_episode_by_path(folder / "1 - Díl.mp3")
            self.assertEqual(episode.image_path, str(folder / "cover.jpg"))  # type: ignore[union-attr]

    async def test_a_part_with_its_own_image_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            own = folder / "1 - Díl.jpg"
            own.write_bytes(self.image)
            repo, folder = await self._work_over_files(tmp, image_path=own)
            (folder / "cover.jpg").write_bytes(self.image)
            service = LibraryService(repository=repo)

            filled = await service.refresh("series", "hash-1")

            self.assertEqual(filled.images, 0)  # type: ignore[union-attr]

    async def test_importing_the_folder_takes_a_cover_that_appeared_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, folder = await self._work_over_files(tmp)
            (folder / "cover.jpg").write_bytes(self.image)

            await LibraryScan(repository=repo, download_path=folder).sync_all()

            episode = await repo.find_episode_by_path(folder / "1 - Díl.mp3")
            self.assertEqual(episode.image_path, str(folder / "cover.jpg"))  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
