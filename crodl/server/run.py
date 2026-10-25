import uvicorn
import asyncio
from crodl.library.database import init_db
from crodl.settings import SERVER_HOST, SERVER_PORT


def start(reload: bool = False):
    """
    Starts the FastAPI web server.

    `reload` is off by default, and that is not a detail: uvicorn's reloader
    watches the *working directory*, and without `watchfiles` (`StatReload`) it
    walks that whole tree four times a second - start the server from a project
    with `node_modules` in it and the idle server eats half a CPU core. For
    development, ask for it: `cro-dl --reload server`.
    """
    # Check if we are already in an event loop
    try:
        asyncio.get_running_loop()
        # If we are here, a loop is running.
        # But init_db() was already awaited in main() group!
    except RuntimeError:
        # No loop running, we can safely run init_db
        asyncio.run(init_db())

    # uvicorn.run is synchronous and starts its own event loop for the server
    uvicorn.run(
        "crodl.server.app:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=reload,
    )


if __name__ == "__main__":
    start()
