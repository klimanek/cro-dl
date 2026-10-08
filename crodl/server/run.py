import uvicorn
import asyncio
from crodl.library.database import init_db
from crodl.settings import SERVER_HOST, SERVER_PORT


def start():
    """Starts the FastAPI web server."""
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
        reload=True,
    )


if __name__ == "__main__":
    start()
