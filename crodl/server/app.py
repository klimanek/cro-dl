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
    """Render the main library web interface."""
    try:
        repo = LibraryRepository()
        episodes = await repo.get_all_episodes()
        
        processed_episodes = []
        for ep in episodes:
            ep_dict = ep.model_dump()
            
            # Safe path processing
            try:
                rel_audio = os.path.relpath(ep.local_path, DOWNLOAD_PATH)
                ep_dict["audio_url"] = f"/library/{rel_audio}"
                
                if ep.image_path:
                    rel_img = os.path.relpath(ep.image_path, DOWNLOAD_PATH)
                    ep_dict["thumb_url"] = f"/library/{rel_img}"
                else:
                    ep_dict["thumb_url"] = None
            except Exception:
                ep_dict["audio_url"] = "#"
                ep_dict["thumb_url"] = None
                
            processed_episodes.append(ep_dict)

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"episodes": processed_episodes}
        )
    except Exception as e:
        # Return the traceback to the browser for debugging
        error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
        return PlainTextResponse(error_msg, status_code=500)
