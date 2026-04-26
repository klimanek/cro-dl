import os
import traceback
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, PlainTextResponse

from crodl.server.api import router as api_router
from crodl.persistence.repository import LibraryRepository
from crodl.settings import DOWNLOAD_PATH

# Get the path to the current file to locate templates
current_dir = os.path.dirname(os.path.realpath(__file__))
template_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=template_dir)

app = FastAPI(
    title="CRo-DL Library",
    description="Local library for Czech Radio downloads",
    version="1.0.0"
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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main library web interface showing unique shows and series."""
    try:
        repo = LibraryRepository()
        shows = await repo.get_all_shows()
        series = await repo.get_all_series()
        all_episodes = await repo.get_all_episodes()
        
        unique_collections = {}
        
        # 1. Process Series
        for sr in series:
            episodes = await repo.get_episodes_by_series(sr.id)
            if not episodes: continue
            
            thumb_url = None
            if episodes[0].image_path:
                rel_img = os.path.relpath(episodes[0].image_path, DOWNLOAD_PATH)
                thumb_url = f"/library/{rel_img}"
                
            unique_collections[sr.title] = {
                "type": "series",
                "id": sr.id,
                "title": sr.title,
                "thumb_url": thumb_url,
                "count": len(episodes)
            }

        # 2. Process Shows
        for s in shows:
            if s.title in unique_collections:
                episodes = await repo.get_episodes_by_show(s.id)
                unique_collections[s.title]["count"] = max(unique_collections[s.title]["count"], len(episodes))
                continue
                
            episodes = await repo.get_episodes_by_show(s.id)
            if not episodes: continue
            
            thumb_url = None
            if episodes[0].image_path:
                rel_img = os.path.relpath(episodes[0].image_path, DOWNLOAD_PATH)
                thumb_url = f"/library/{rel_img}"
                
            unique_collections[s.title] = {
                "type": "show",
                "id": s.id,
                "title": s.title,
                "thumb_url": thumb_url,
                "count": len(episodes)
            }

        # 3. Process Orphaned Episodes (Manual Imports)
        orphans = [e for e in all_episodes if not e.show_id and not e.series_id]
        if orphans:
            unique_collections["_orphans"] = {
                "type": "orphans",
                "id": "orphans",
                "title": "Místní soubory",
                "thumb_url": None,
                "count": len(orphans)
            }

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"collections": list(unique_collections.values())}
        )
    except Exception as e:
        error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
        return PlainTextResponse(error_msg, status_code=500)

@app.get("/detail/{ctype}/{id}", response_class=HTMLResponse)
async def detail(request: Request, ctype: str, id: str):
    """Render the detail page for a show, series or orphaned episodes."""
    try:
        repo = LibraryRepository()
        
        if ctype == "show":
            content = await repo.get_show(id)
            episodes = await repo.get_episodes_by_show(id)
        elif ctype == "series":
            content = await repo.get_series(id)
            episodes = await repo.get_episodes_by_series(id)
        else:
            # Handle orphaned episodes
            content = type('obj', (object,), {'title': 'Místní soubory', 'description': 'Soubory importované bez metadat.'})
            all_episodes = await repo.get_all_episodes()
            episodes = [e for e in all_episodes if not e.show_id and not e.series_id]
            
        if not content:
            return PlainTextResponse("Not found", status_code=404)

        processed_episodes = []
        for ep in episodes:
            ep_dict = ep.model_dump()
            try:
                rel_audio = os.path.relpath(ep.local_path, DOWNLOAD_PATH)
                ep_dict["audio_url"] = f"/library/{rel_audio}"
            except Exception:
                ep_dict["audio_url"] = "#"
            processed_episodes.append(ep_dict)

        return templates.TemplateResponse(
            request=request,
            name="detail.html",
            context={
                "content": content,
                "episodes": processed_episodes,
                "type": ctype
            }
        )
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)
