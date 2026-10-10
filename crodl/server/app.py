import asyncio
import os
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
)

from crodl.library import roots
from crodl.library.database import init_db
from crodl.library.repository import SqliteLibraryRepository
from crodl.library.service import LibraryService
from crodl.library.tags import read_tags_now
from crodl.server.queue import queue_items
from crodl.program.content import Collection
from crodl.server.access_log import log_readable_paths
from crodl.server.api import router as api_router
from crodl.server.browse import listing
from crodl.server.checks import checker
from crodl.server.downloads import downloads
from crodl.server.format import (  # noqa: I001
    GENRES_SHOWN,
    added_line,
    changed_line,
    check_report,
    curated_report,
    czech_count,
    czech_datetime,
    expired_parts_label,
    link_report,
    media_url,
    new_parts_label,
    parts_label,
    records_label,
    refresh_report,
    settings_report,
    tags_report,
    upcoming_parts_label,
)
from crodl.settings import (
    DOWNLOAD_PATH,
    SERVER_HOST,
    SERVER_PORT,
    UPDATE_CHECK_HOURS,
)

# The addresses the server itself runs on: the only origins that may talk to it.
LOCAL_ORIGINS = [
    f"http://{SERVER_HOST}:{SERVER_PORT}",
    f"http://localhost:{SERVER_PORT}",
]

# A request the server acts on must have been addressed to the loopback
# interface; a form post has no CORS to stop it (see `check_same_origin`).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Czech names of the kinds of work the library knows.
TYPE_LABELS = {"show": "Pořad", "series": "Seriál", "orphans": "Bez metadat"}

# The cookie that remembers whether the edit controls are shown.
EDIT_COOKIE = "edit"


def file_tags(path: Optional[str]) -> dict[str, str]:
    """What a part's file says about itself (edit mode shows it, and offers it)."""
    if not path:
        return {}

    return read_tags_now(Path(path))


def template_helpers(request: Request) -> dict[str, Any]:
    """What every template can use: labels, formatting, the editing mode."""
    return {
        "media_url": media_url,
        "parts_label": parts_label,
        "records_label": records_label,
        "new_parts_label": new_parts_label,
        "upcoming_parts_label": upcoming_parts_label,
        "expired_parts_label": expired_parts_label,
        "type_labels": TYPE_LABELS,
        "czech_datetime": czech_datetime,
        "czech_count": czech_count,
        "added_line": added_line,
        "changed_line": changed_line,
        "check_report": check_report,
        "file_tags": file_tags,
        "genres_shown": GENRES_SHOWN,
        "missing_roots": [str(path) for path in roots.missing()],
        "edit_mode": edit_mode_on(request),
        "check": checker.state,
    }


def edit_mode_on(request: Request) -> bool:
    """
    Whether the page should show its editing controls.

    Off by default: the edit forms are there to be reached, not to be looked at
    on every visit (see the "Režim úprav" switch in the top bar).
    """
    return request.cookies.get(EDIT_COOKIE) == "1"


def local_target(url: str) -> str:
    """Where a redirect may lead: a page on this server, nothing else."""
    if not url.startswith("/") or url.startswith("//"):
        return "/"

    return url


# Get the path to the current file to locate templates
current_dir = os.path.dirname(os.path.realpath(__file__))
template_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=template_dir)
templates.context_processors.append(template_helpers)

#: How long to wait after start before the first look for new parts, so that the
#: server is answering before anything reaches out to the network.
UPDATE_CHECK_DELAY = 20


async def watch_for_new_parts() -> None:
    """
    Looks for new parts shortly after start, then every `UPDATE_CHECK_HOURS`.

    Seeing a new episode of a series without asking is the point; the run goes
    through the same checker the button uses, so the top bar shows its outcome.
    A check that fails (the network is away, the API has a bad day) must never
    take the server down, and `run()` only records it.
    """
    if not UPDATE_CHECK_HOURS:
        return  # switched off in settings

    await asyncio.sleep(UPDATE_CHECK_DELAY)

    while True:
        await checker.run()
        await asyncio.sleep(UPDATE_CHECK_HOURS * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Make sure the library exists, then watch it for new parts."""
    await init_db()
    # Which folders the library keeps its audio in (the default one, plus any
    # added by hand), so the pages know what may be served.
    await library_service().load_roots()
    watcher = asyncio.create_task(watch_for_new_parts())

    try:
        yield
    finally:
        watcher.cancel()


app = FastAPI(
    title="CRo-DL Library",
    description="Local library for Czech Radio downloads",
    version="1.0.0",
    lifespan=lifespan,
)

# Czech paths in the access log, not percent-escapes (also under --reload,
# where the app module is imported by the worker process).
log_readable_paths()

# The player's script and whatever else belongs to the pages: our own files, not
# the user's library (which is served through /library, one known file at a time).
app.mount("/static", StaticFiles(directory=Path(current_dir) / "static"), name="static")

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
        service = library_service()
        items = await service.overview()
        genres = await service.genres()
        # A genre in the URL narrows the grid to that genre (the top bar links).
        wanted = request.query_params.get("zanr", "")
        collections = (
            [item for item in items if item.genre == wanted] if wanted else items
        )
        deleted = request.query_params.get("smazano", "")

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "collections": collections,
                "works": len(collections),
                "parts": sum(item.count for item in collections),
                "deleted": int(deleted) if deleted.isdigit() else 0,
                "genres": genres,
                "active_genre": wanted,
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
            context={
                "content": content,
                "episodes": episodes,
                "type": ctype,
                "report": refresh_report(request.query_params.get("obnoveno", ""))
                or link_report(request.query_params.get("odkaz", ""))
                or tags_report(request.query_params.get("tagy", ""))
                or curated_report(request.query_params.get("upraveno", "")),
                "source_url": await library_service().source_url(content_id),
                "genres": await library_service().genres(),
            },
        )
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)


@app.get("/edit-mode")
async def switch_edit_mode(request: Request, on: str = "0", next: str = "/"):
    """
    Show or hide the editing controls.

    A link, not a form: it changes a view preference and nothing else. The choice
    goes into a cookie so it survives the next page.
    """
    response = RedirectResponse(local_target(next), status_code=303)
    response.set_cookie(
        EDIT_COOKIE, "1" if on == "1" else "0", httponly=True, samesite="lax"
    )

    return response


@app.post("/updates/check")
async def check_new_parts(request: Request):
    """
    Look for parts the Czech Radio released since.

    The check runs in the background and the library shows a spinner until it is
    done (a tick or a cross afterwards); the timer in the app uses the same one.
    """
    check_same_origin(request)
    checker.start()

    return RedirectResponse("/", status_code=303)


@app.post("/detail/{ctype}/{content_id}/missing")
async def download_new_parts(request: Request, ctype: str, content_id: str):
    """Queue the parts this work gained since it was downloaded."""
    check_same_origin(request)
    service = library_service()
    missing = await service.missing_parts(ctype, content_id)
    # Only what can still be fetched: expired and un-aired parts are not news.
    parts = [part for part in missing or [] if part.fetchable]
    content, episodes = await service.detail(ctype, content_id)

    if not parts or content is None or not episodes:
        # Nothing to fetch - just show the work.
        return RedirectResponse(f"/detail/{ctype}/{content_id}", status_code=303)

    job = downloads.start_missing(
        content.title,
        parts,
        # The parts land next to their siblings and belong to the same work.
        directory=Path(episodes[0].local_path).parent,
        collection=Collection(
            uuid=content_id,
            type=ctype,
            title=content.title,
            description=content.description,
            # The parts share the work's image; without this each would fetch
            # its own copy next to itself instead of reusing its cover.
            shared_asset_url=next(
                (part.asset_url for part in parts if part.asset_url), None
            ),
        ),
    )

    return RedirectResponse(f"/downloads/{job.id}", status_code=303)


@app.post("/downloads")
async def start_download(request: Request):
    """Queue a download and send the browser to its page."""
    check_same_origin(request)
    url = (await form_fields(request)).get("url", "").strip()

    if not url:
        return RedirectResponse("/downloads", status_code=303)

    job = downloads.start(url)

    return RedirectResponse(f"/downloads/{job.id}", status_code=303)


@app.get("/downloads", response_class=HTMLResponse)
async def download_list(request: Request):
    """The downloads started from here, newest first."""
    return templates.TemplateResponse(
        request=request,
        name="downloads.html",
        context={"jobs": [job.as_dict() for job in downloads.jobs()]},
    )


@app.get("/downloads/{job_id}", response_class=HTMLResponse)
async def download_detail(request: Request, job_id: str):
    """One download; the page refreshes itself while it runs."""
    job = downloads.get(job_id)

    if job is None:
        return PlainTextResponse("Not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="download.html",
        context={"job": job.as_dict()},
    )


@app.post("/detail/{ctype}/{content_id}/edit")
async def curate_work(request: Request, ctype: str, content_id: str):
    """Save the name, genre and description a person gave a work."""
    check_same_origin(request)
    service = library_service()

    if not await service.curate_work(ctype, content_id, await form_fields(request)):
        return PlainTextResponse("Not found", status_code=404)

    # The genre (and whatever else the parts carry) belongs in their files too.
    written = await service.write_work_tags(ctype, content_id)

    return RedirectResponse(
        f"/detail/{ctype}/{content_id}?upraveno={written}", status_code=303
    )


@app.post("/detail/{ctype}/{content_id}/parts/{part_id}/edit")
async def curate_part(request: Request, ctype: str, content_id: str, part_id: str):
    """Save hand-edited metadata for one part of a work."""
    check_same_origin(request)

    if not await library_service().curate_part(part_id, await form_fields(request)):
        return PlainTextResponse("Not found", status_code=404)

    return RedirectResponse(f"/detail/{ctype}/{content_id}", status_code=303)


@app.get("/fronta")
async def queue_page(request: Request):
    """The player's queue as a page of its own (the script fills it in)."""
    return templates.TemplateResponse(request=request, name="queue.html")


@app.get("/settings")
async def settings(request: Request):
    """Which folders make up the library, and importing one of them."""
    stored = await library_service().stored_roots()
    folders = [
        {
            "path": row.path,
            "missing": not Path(row.path).is_dir(),
            "default": row.path == str(DOWNLOAD_PATH),
        }
        for row in stored
    ]

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "folders": folders,
            # `?prochazet=` (even empty) asks for the folder browser; see browse.py.
            "browse": listing(request.query_params["prochazet"])
            if "prochazet" in request.query_params
            else None,
            "report": settings_report(
                added=request.query_params.get("pridano", ""),
                files=request.query_params.get("souboru", ""),
                error=request.query_params.get("chyba", ""),
                removed=request.query_params.get("odebrano", ""),
            ),
        },
    )


@app.post("/settings/roots")
async def add_root(request: Request):
    """Add a folder of audio to the library, and import what is in it."""
    check_same_origin(request)
    fields = await form_fields(request)
    service = library_service()
    added = await service.add_root(fields.get("path", ""))

    if added is None:
        return RedirectResponse("/settings?chyba=1", status_code=303)

    imported = await service.import_root(added.path)

    return RedirectResponse(
        f"/settings?pridano={quote(added.path)}&souboru={imported.get('success', 0)}",
        status_code=303,
    )


@app.post("/settings/roots/remove")
async def remove_root(request: Request):
    """Forget a folder; its works stay in the library (the files are untouched)."""
    check_same_origin(request)
    fields = await form_fields(request)

    if not await library_service().forget_root(fields.get("path", "")):
        return RedirectResponse("/settings?chyba=1", status_code=303)

    return RedirectResponse("/settings?odebrano=1", status_code=303)


@app.post("/detail/{ctype}/{content_id}/link")
async def set_source_url(request: Request, ctype: str, content_id: str):
    """Remember the mujrozhlas.cz page a work came from (edit mode)."""
    check_same_origin(request)
    fields = await form_fields(request)
    saved = await library_service().set_source_url(
        ctype, content_id, fields.get("url", "")
    )

    return RedirectResponse(
        f"/detail/{ctype}/{content_id}?odkaz={'ok' if saved else 'ne'}",
        status_code=303,
    )


@app.get("/detail/{ctype}/{content_id}/queue")
async def work_queue(ctype: str, content_id: str) -> dict[str, Any]:
    """The work's parts as queue entries (the player appends them in the browser)."""
    content, episodes = await library_service().detail(ctype, content_id)

    if content is None:
        raise HTTPException(status_code=404, detail="Unknown work")

    return {"items": queue_items(content, episodes)}


@app.post("/detail/{ctype}/{content_id}/tags")
async def write_work_tags(request: Request, ctype: str, content_id: str):
    """Write what the library knows into every part's file (edit mode)."""
    check_same_origin(request)
    written = await library_service().write_work_tags(ctype, content_id)

    return RedirectResponse(
        f"/detail/{ctype}/{content_id}?tagy={written}", status_code=303
    )


@app.post("/detail/{ctype}/{content_id}/parts/{part_id}/tags")
async def write_part_tags(request: Request, ctype: str, content_id: str, part_id: str):
    """Write the tags a person edited into one part's file (edit mode)."""
    check_same_origin(request)
    fields = await form_fields(request)
    service = library_service()
    _, episodes = await service.detail(ctype, content_id)
    episode = next((ep for ep in episodes or [] if ep.uuid == part_id), None)

    if episode is None or not episode.local_path:
        return PlainTextResponse("Not found", status_code=404)

    track = fields.get("track", "").strip()
    written = await service.write_part_tags(
        Path(episode.local_path),
        title=fields.get("title") or None,
        author=fields.get("author") or None,
        album=fields.get("album") or None,
        genre=fields.get("genre") or None,
        track=int(track) if track.isdigit() else None,
    )

    return RedirectResponse(
        f"/detail/{ctype}/{content_id}?tagy={1 if written else 0}", status_code=303
    )


@app.post("/detail/{ctype}/{content_id}/refresh")
async def refresh_work(request: Request, ctype: str, content_id: str):
    """Ask the content API for what the library is missing about a work."""
    check_same_origin(request)
    filled = await library_service().refresh(ctype, content_id)

    if filled is None:
        return RedirectResponse(
            f"/detail/{ctype}/{content_id}?obnoveno=none", status_code=303
        )

    return RedirectResponse(
        f"/detail/{ctype}/{content_id}?obnoveno={filled.fields}-{filled.images}",
        status_code=303,
    )


@app.get("/detail/{ctype}/{content_id}/delete", response_class=HTMLResponse)
async def confirm_delete(request: Request, ctype: str, content_id: str):
    """Ask before a work leaves the library."""
    content, episodes = await library_service().detail(ctype, content_id)

    if content is None:
        return PlainTextResponse("Not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="delete.html",
        context={"content": content, "type": ctype, "parts": len(episodes)},
    )


@app.post("/detail/{ctype}/{content_id}/delete")
async def delete_work(request: Request, ctype: str, content_id: str):
    """Remove a work from the library; the files on disk stay where they are."""
    check_same_origin(request)
    removed = await library_service().forget(ctype, content_id)

    return RedirectResponse(f"/?smazano={removed}", status_code=303)
