"""Starting the web server from the CLI's event loop."""

import sys
import unittest
from unittest import mock

from crodl.server import run as server_run


class TestServerStart(unittest.IsolatedAsyncioTestCase):
    """`cro-dl server` must not ask uvicorn to start a second event loop."""

    async def asyncSetUp(self) -> None:
        self.init_db = mock.AsyncMock()
        patcher = mock.patch.object(server_run, "init_db", self.init_db)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_the_server_serves_on_the_calling_loop(self):
        with mock.patch.object(server_run.uvicorn, "Server") as server_cls:
            server = server_cls.return_value
            server.serve = mock.AsyncMock()

            await server_run.start()

        server.serve.assert_awaited_once_with()
        self.init_db.assert_awaited_once()

    async def test_reload_runs_the_reloader_in_a_child_process(self):
        with mock.patch.object(server_run, "_run_reloader") as reloader:
            await server_run.start(reload=True)

        reloader.assert_called_once_with()


class TestTheReloader(unittest.TestCase):
    def test_it_runs_uvicorn_as_a_module_with_reload(self):
        with mock.patch.object(server_run.subprocess, "run") as run:
            server_run._run_reloader()

        command = run.call_args.args[0]

        self.assertEqual(command[:3], [sys.executable, "-m", "uvicorn"])
        self.assertEqual(command[-1], "--reload")
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
