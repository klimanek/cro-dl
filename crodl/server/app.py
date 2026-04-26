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
    """Render the main library web interface showing shows and series."""
    try:
        repo = LibraryRepository()
        shows = await repo.get_all_shows()
        series = await repo.get_all_series()
        
        collections = []
        
        # Process Shows
        for s in shows:
            # Get first episode to extract thumbnail
            episodes = await repo.get_episodes_by_show(s.id)
            if not episodes: continue
            
            thumb_url = None
            if episodes[0].image_path:
                rel_img = os.path.relpath(episodes[0].image_path, DOWNLOAD_PATH)
                thumb_url = f"/library/{rel_img}"
                
            collections.append({
                "type": "show",
                "id": s.id,
                "title": s.title,
                "description": s.description or episodes[0].description,
                "thumb_url": thumb_url,
                "count": len(episodes)
            })

        # Process Series (avoid duplicates if series is also a show)
        show_ids = [s.id for s in shows]
        for sr in series:
            if sr.id in show_ids: continue
            
            episodes = await repo.get_episodes_by_series(sr.id)
            if not episodes: continue
            
            thumb_url = None
            if episodes[0].image_path:
                rel_img = os.path.relpath(episodes[0].image_path, DOWNLOAD_PATH)
                thumb_url = f"/library/{rel_img}"
                
            collections.append({
                "type": "series",
                "id": sr.id,
                "title": sr.title,
                "description": sr.description or episodes[0].description,
                "thumb_url": thumb_url,
                "count": len(episodes)
            })

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"collections": collections}
        )
    except Exception as e:
        error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
        return PlainTextResponse(error_msg, status_code=500)

@app.get("/detail/{ctype}/{id}", response_class=HTMLResponse)
async def detail(request: Request, ctype: str, id: str):
    """Render the detail page for a show or series with episode list."""
    try:
        repo = LibraryRepository()
        if ctype == "show":
            content = await repo.get_show(id)
            episodes = await repo.get_episodes_by_show(id)
        else:
            content = await repo.get_series(id)
            episodes = await repo.get_episodes_by_series(id)
            
        if not content:
            return PlainTextResponse("Not found", status_code=404)

        processed_episodes = []
        for ep in episodes:
            ep_dict = ep.model_dump()
            rel_audio = os.path.relpath(ep.local_path, DOWNLOAD_PATH)
            ep_dict["audio_url"] = f"/library/{rel_audio}"
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
