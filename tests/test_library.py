import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from crodl.library.models import Episode
from crodl.library.repository import (
    LibraryRepository,
    SqliteLibraryRepository,
    parse_since,
    to_naive_utc,
)


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
    ) -> None:
        self.uuid = uuid
        self.title = title
        self.since = since
        self.description = description
        self.author = author
        self.audio_formats = ["mp3", "hls"] if audio_formats is None else audio_formats


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
        self.assertEqual(stored.author, "Autor")
        self.assertEqual(stored.description, "Popis")
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


class TestRepositoryProtocol(unittest.TestCase):
    def test_sqlite_repository_implements_the_protocol(self):
        self.assertIsInstance(SqliteLibraryRepository(), LibraryRepository)
