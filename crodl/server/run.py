"""Starting the web library."""

import asyncio
import subprocess
import sys

import uvicorn

from crodl.library.database import init_db
from crodl.settings import SERVER_HOST, SERVER_PORT


async def start(reload: bool = False) -> None:
    """
    Starts the FastAPI web server in the caller's event loop.

    The CLI is already inside asyncclick's event loop, so `uvicorn.run()` cannot
    be called here - it starts a loop of its own and dies with "Runner.run()
    cannot be called from a running event loop". `Server.serve()` runs the
    server on the loop that is already there.

    `reload` is off by default, and that is not a detail: uvicorn's reloader
    watches the *working directory*, and without `watchfiles` (`StatReload`) it
    walks that whole tree four times a second - start the server from a project
    with `node_modules` in it and the idle server eats half a CPU core. For
    development, ask for it: `cro-dl --reload server`. The reloader needs a
    process (and an event loop) of its own, so it runs as a child process.
    """
    await init_db()

    if reload:
        await asyncio.to_thread(_run_reloader)
        return

    config = uvicorn.Config("crodl.server.app:app", host=SERVER_HOST, port=SERVER_PORT)
    await uvicorn.Server(config).serve()


def _run_reloader() -> None:
    """Runs uvicorn's reload supervisor in a child process."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "crodl.server.app:app",
            "--host",
            SERVER_HOST,
            "--port",
            str(SERVER_PORT),
            "--reload",
        ],
        check=True,
    )


if __name__ == "__main__":
    asyncio.run(start())
