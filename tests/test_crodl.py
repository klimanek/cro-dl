import unittest
from pathlib import Path
from unittest import mock

from crodl import CroDL
from crodl.program.content import Collection
from crodl.settings import AudioFormat


class TestIsDomainSupported(unittest.TestCase):
    def setUp(self):
        self.dl = CroDL()

    def test_supported_domain(self):
        url = "https://www.mujrozhlas.cz"
        self.assertTrue(self.dl.is_domain_supported(url))

    def test_unsupported_domain(self):
        url = "https://vltava.rozhlas.cz"
        self.assertFalse(self.dl.is_domain_supported(url))

    def test_empty_url(self):
        url = ""
        self.assertFalse(self.dl.is_domain_supported(url))

    def test_invalid_url(self):
        url = " invalid url "
        self.assertFalse(self.dl.is_domain_supported(url))


class TestLibraryHook(unittest.IsolatedAsyncioTestCase):
    """The facade is what connects the core to the library (no DB in the core)."""

    def _make_dl(self, library):
        return CroDL(client=mock.Mock(), library=library)

    def _make_content(self):
        content = mock.Mock()
        content.title = "Dílo"
        content.download = mock.AsyncMock()
        return content

    async def test_finished_download_is_stored_in_the_library(self):
        library = mock.Mock()
        library.save_download = mock.AsyncMock()
        content = self._make_content()

        await self._make_dl(library).download(content, audio_format=AudioFormat.MP3)

        work, path = mock.Mock(), Path("/tmp/3 - Díl.mp3")
        hook = content.download.call_args.kwargs["on_downloaded"]
        self.assertIsNotNone(hook)

        await hook(work, path)

        library.save_download.assert_awaited_once_with(
            work, path, audio_format="mp3", collection=None
        )

    async def test_the_work_a_part_belongs_to_is_handed_over(self):
        library = mock.Mock()
        library.save_download = mock.AsyncMock()
        content = self._make_content()
        collection = Collection(uuid="series-1", type="series", title="Seriál")

        await self._make_dl(library).download(content, audio_format=AudioFormat.MP3)

        work, path = mock.Mock(), Path("/tmp/library/3 - Díl.mp3")
        hook = content.download.call_args.kwargs["on_downloaded"]
        await hook(work, path, collection)

        library.save_download.assert_awaited_once_with(
            work, path, audio_format="mp3", collection=collection
        )

    async def test_without_a_library_nothing_is_stored(self):
        content = self._make_content()

        await self._make_dl(None).download(content, audio_format=AudioFormat.MP3)

        hook = content.download.call_args.kwargs["on_downloaded"]
        # Must simply do nothing instead of raising.
        await hook(mock.Mock(), Path("/tmp/a.mp3"))


if __name__ == "__main__":
    unittest.main()
