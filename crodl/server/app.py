import os
import traceback
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
)

from crodl.server.access_log import log_readable_paths
from crodl.server.api import router as api_router
from crodl.library.repository import SqliteLibraryRepository
from crodl.library.service import LibraryService
from crodl.settings import DOWNLOAD_PATH, SERVER_HOST, SERVER_PORT

# The addresses the server itself runs on: the only origins that may talk to it.
LOCAL_ORIGINS = [
    f"http://{SERVER_HOST}:{SERVER_PORT}",
    f"http://localhost:{SERVER_PORT}",
]

# A request the server acts on must have been addressed to the loopback
# interface; a form post has no CORS to stop it (see `check_same_origin`).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


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

# Czech paths in the access log, not percent-escapes (also under --reload,
# where the app module is imported by the worker process).
log_readable_paths()

# Enable CORS: the UI is served from this very origin, so only the local
# addresses the server itself runs on are ever allowed (a future SPA too).
app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")


def library_service() -> LibraryService:
    """The one place the routes reach the library through."""
    return LibraryService(repository=SqliteLibraryRepository())


async def form_fields(request: Request) -> dict[str, str]:
    """
    The fields of the url-encoded form the UI posts.

    Read by hand on purpose: Starlette's form parsing (and FastAPI's `Form()`)
    needs `python-multipart`, which cro-dl does not depend on - the UI posts
    plain urlencoded forms and nothing else.
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/x-www-form-urlencoded"):
        raise HTTPException(status_code=400, detail="Expected a form body")

    body = (await request.body()).decode("utf-8")

    return {
        key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()
    }


def check_same_origin(request: Request) -> None:
    """
    Refuse a write that did not come from a page on this very server.

    Two things are checked, because either alone is too weak: the request must
    have been addressed to the loopback interface (so a name that merely
    resolves to 127.0.0.1 - DNS rebinding - does not pass) and, when the browser
    sends an `Origin`, it must be this server's own origin. Comparing against
    the request's own host rather than a configured port matters: the server can
    perfectly well be started on another one.
    """
    host = request.headers.get("host", "")
    hostname = urlsplit(f"//{host}").hostname or ""

    if hostname not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="Not a local request")

    origin = request.headers.get("origin")

    if origin is not None and origin != f"{request.url.scheme}://{host}":
        raise HTTPException(status_code=403, detail="Cross-origin request refused")


@app.get("/library/{path:path}")
async def media(path: str):
    """
    Serve one downloaded file.

    The download directory is not mounted as a whole: it also holds the segment
    folders, the log and `library.db`, and those have no business being URLs.
    Only files the library stored - and files inside the directory - get through.
    """
    target = await library_service().media_file(path)

    if target is None:
        raise HTTPException(status_code=404, detail="File not found")

    # FileResponse answers Range requests, so the player can seek.
    return FileResponse(target)


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


@app.post("/detail/{ctype}/{content_id}/edit")
async def curate_work(request: Request, ctype: str, content_id: str):
    """Save the name and description a person gave a work."""
    check_same_origin(request)

    if not await library_service().curate_work(
        ctype, content_id, await form_fields(request)
    ):
        return PlainTextResponse("Not found", status_code=404)

    return RedirectResponse(f"/detail/{ctype}/{content_id}", status_code=303)


@app.post("/detail/{ctype}/{content_id}/parts/{part_id}/edit")
async def curate_part(request: Request, ctype: str, content_id: str, part_id: str):
    """Save hand-edited metadata for one part of a work."""
    check_same_origin(request)

    if not await library_service().curate_part(part_id, await form_fields(request)):
        return PlainTextResponse("Not found", status_code=404)

    return RedirectResponse(f"/detail/{ctype}/{content_id}", status_code=303)
