import uvicorn
import asyncio
from crodl.persistence.database import init_db

def start():
    """Starts the FastAPI web server."""
    # Ensure DB is initialized before starting the server
    # We use a small trick to run sync in uvicorn's loop if needed, 
    # but init_db is async, so we should call it properly.
    
    # Uvicorn handles the loop, so we can use its lifespan or just init here.
    # For simplicity in this script:
    asyncio.run(init_db())
    
    uvicorn.run("crodl.server.app:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    start()
