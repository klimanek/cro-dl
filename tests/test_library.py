import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    return SqliteLibraryRepository(session_factory=factory)


class TestSqliteLibraryRepository(unittest.IsolatedAsyncioTestCase):
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


class TestLibraryQueries(unittest.IsolatedAsyncioTestCase):
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


class TestLibraryScan(unittest.IsolatedAsyncioTestCase):
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

        download.assert_awaited_once()
        self.assertIsNotNone(episode)
        self.assertEqual(
            str(episode.image_path),
            str(cover),  # type: ignore[union-attr]
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


if __name__ == "__main__":
    unittest.main()
