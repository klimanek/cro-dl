import os
import traceback
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, PlainTextResponse

from crodl.server.api import router as api_router
from crodl.library.repository import SqliteLibraryRepository
from crodl.library.service import LibraryService
from crodl.settings import DOWNLOAD_PATH


def media_url(path: Optional[str]) -> Optional[str]:
    """URL of a file under the download directory, as served on /library."""
    if not path:
        return None

    try:
        relative = Path(os.path.relpath(path, DOWNLOAD_PATH)).as_posix()
    except ValueError:  # a file on another drive (Windows) has no relative path
        return None

    return "/library/" + quote(relative)


def parts_label(count: int) -> str:
    """Czech plural of "díl": 1 díl, 3 díly, 12 dílů."""
    if count == 1:
        return "1 díl"
    if 2 <= count <= 4:
        return f"{count} díly"

    return f"{count} dílů"


# Czech names of the kinds of work the library knows.
TYPE_LABELS = {"show": "Pořad", "series": "Seriál", "orphans": "Bez metadat"}


def template_helpers(request: Request) -> dict[str, Any]:
    """What every template can use: media URLs, Czech labels, part counts."""
    return {
        "media_url": media_url,
        "parts_label": parts_label,
        "type_labels": TYPE_LABELS,
    }


# Get the path to the current file to locate templates
current_dir = os.path.dirname(os.path.realpath(__file__))
template_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=template_dir)
templates.context_processors.append(template_helpers)

app = FastAPI(
    title="CRo-DL Library",
    description="Local library for Czech Radio downloads",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve downloaded files
if os.path.exists(DOWNLOAD_PATH):
    app.mount("/library", StaticFiles(directory=str(DOWNLOAD_PATH)), name="library")

# Include API routes
app.include_router(api_router, prefix="/api")


def library_service() -> LibraryService:
    """The one place the routes reach the library through."""
    return LibraryService(repository=SqliteLibraryRepository())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the library: one card per work, each with its artwork."""
    try:
        collections = await library_service().overview()

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "collections": collections,
                "works": len(collections),
                "parts": sum(item.count for item in collections),
            },
        )
    except Exception as e:
        error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
        return PlainTextResponse(error_msg, status_code=500)


@app.get("/detail/{ctype}/{content_id}", response_class=HTMLResponse)
async def detail(request: Request, ctype: str, content_id: str):
    """Render one work with its parts, ready to play."""
    try:
        content, episodes = await library_service().detail(ctype, content_id)

        if content is None:
            return PlainTextResponse("Not found", status_code=404)

        return templates.TemplateResponse(
            request=request,
            name="detail.html",
            context={"content": content, "episodes": episodes, "type": ctype},
        )
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)
