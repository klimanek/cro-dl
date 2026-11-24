"""The PyPI version check: what is newer, what is cached, and what the CLI says."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import requests

from crodl.main import announce_update
from crodl.tools import version_check


def response_with(version: str) -> mock.Mock:
    """A PyPI answer carrying one release version."""
    response = mock.Mock()
    response.json.return_value = {"info": {"version": version}}
    response.raise_for_status.return_value = None
    return response


class TestIsNewer(unittest.TestCase):
    def test_a_later_release_is_newer(self):
        self.assertTrue(version_check.is_newer("2.2.0", "2.1.2"))

    def test_the_same_version_is_not(self):
        self.assertFalse(version_check.is_newer("2.1.2", "2.1.2"))

    def test_an_older_version_is_not(self):
        self.assertFalse(version_check.is_newer("2.0.0", "2.1.2"))

    def test_garbage_is_not_newer(self):
        self.assertFalse(version_check.is_newer("not a version", "2.1.2"))


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "cache.json"
        version_check._known = None

    def tearDown(self):
        self.tmp.cleanup()
        version_check._known = None

    def write_cache(self, latest: str, checked: datetime) -> None:
        self.cache.write_text(
            json.dumps({"checked_at": checked.isoformat(), "latest": latest}),
            encoding="utf-8",
        )

    @mock.patch("crodl.tools.version_check.requests.get")
    def test_a_newer_release_is_found_and_cached(self, get):
        get.return_value = response_with("2.2.0")

        found = version_check.check(current="2.1.2", cache=self.cache)

        self.assertEqual(found, version_check.NewVersion("2.1.2", "2.2.0"))
        self.assertEqual(version_check.known(), found)
        self.assertEqual(
            json.loads(self.cache.read_text(encoding="utf-8"))["latest"], "2.2.0"
        )
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["timeout"], version_check.TIMEOUT)
        self.assertIn("cro-dl/", get.call_args.kwargs["headers"]["User-Agent"])

    @mock.patch("crodl.tools.version_check.requests.get")
    def test_a_fresh_cache_is_not_asked_again(self, get):
        self.write_cache("2.2.0", datetime.now(timezone.utc))

        found = version_check.check(current="2.1.2", cache=self.cache)

        self.assertEqual(found, version_check.NewVersion("2.1.2", "2.2.0"))
        get.assert_not_called()

    @mock.patch("crodl.tools.version_check.requests.get")
    def test_a_stale_cache_is_checked_again(self, get):
        self.write_cache("2.1.3", datetime.now(timezone.utc) - timedelta(days=2))
        get.return_value = response_with("2.2.0")

        found = version_check.check(current="2.1.2", cache=self.cache)

        self.assertEqual(found, version_check.NewVersion("2.1.2", "2.2.0"))
        get.assert_called_once()

    @mock.patch("crodl.tools.version_check.requests.get")
    def test_a_network_failure_is_silent(self, get):
        get.side_effect = requests.RequestException("no network")

        self.assertIsNone(version_check.check(current="2.1.2", cache=self.cache))

    @mock.patch("crodl.tools.version_check.requests.get")
    def test_an_up_to_date_release_is_no_notice(self, get):
        get.return_value = response_with("2.1.2")

        self.assertIsNone(version_check.check(current="2.1.2", cache=self.cache))
        self.assertIsNone(version_check.known())

    @mock.patch("crodl.tools.version_check.requests.get")
    def test_a_stale_cache_answers_when_the_network_is_away(self, get):
        self.write_cache("2.2.0", datetime.now(timezone.utc) - timedelta(days=2))
        get.side_effect = requests.RequestException("no network")

        found = version_check.check(current="2.1.2", cache=self.cache)

        self.assertEqual(found, version_check.NewVersion("2.1.2", "2.2.0"))


class TestTheCLIAnnouncement(unittest.IsolatedAsyncioTestCase):
    async def test_a_newer_release_is_printed(self):
        info = version_check.NewVersion(current="2.1.2", latest="2.2.0")

        with (
            mock.patch.object(
                version_check, "refresh", mock.AsyncMock(return_value=info)
            ),
            mock.patch("crodl.main.print") as output,
        ):
            await announce_update()

        text = " ".join(str(call.args[0]) for call in output.call_args_list)
        self.assertIn("2.2.0", text)
        self.assertIn("pip install --upgrade cro-dl", text)

    async def test_nothing_is_printed_when_up_to_date(self):
        with (
            mock.patch.object(
                version_check, "refresh", mock.AsyncMock(return_value=None)
            ),
            mock.patch("crodl.main.print") as output,
        ):
            await announce_update()

        output.assert_not_called()


if __name__ == "__main__":
    unittest.main()
