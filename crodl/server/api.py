from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from crodl.library.repository import SqliteLibraryRepository
from crodl.library.models import Episode
from crodl.server.downloads import downloads

router = APIRouter()


class DownloadRequest(BaseModel):
    """The body of a request to download a work by its URL."""

    url: str


# Dependency to get the repository
async def get_repo():
    return SqliteLibraryRepository()


@router.get("/episodes", response_model=List[Episode])
async def list_episodes(repo: SqliteLibraryRepository = Depends(get_repo)):
    """Returns a list of all downloaded episodes."""
    return await repo.get_all_episodes()


@router.get("/episodes/{uuid}", response_model=Episode)
async def get_episode(uuid: str, repo: SqliteLibraryRepository = Depends(get_repo)):
    """Returns details of a specific episode."""
    episode = await repo.get_episode(uuid)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/library-stats")
async def get_stats(repo: SqliteLibraryRepository = Depends(get_repo)):
    """Returns basic statistics about the local library."""
    episodes = await repo.get_all_episodes()
    return {
        "total_episodes": len(episodes),
        "total_shows": len(set(e.show_id for e in episodes if e.show_id)),
        "total_series": len(set(e.series_id for e in episodes if e.series_id)),
    }


@router.post("/downloads", status_code=202)
async def start_download(request: DownloadRequest):
    """
    Queues a download and returns the job to watch.

    The download itself runs in the background; poll `/api/downloads/{id}` for
    the state and how many parts are on disk.
    """
    return downloads.start(request.url).as_dict()


@router.get("/downloads")
async def list_downloads():
    """Returns the downloads started from the web, newest first."""
    return [job.as_dict() for job in downloads.jobs()]


@router.get("/downloads/{job_id}")
async def get_download(job_id: str):
    """Returns one download and how far it got."""
    job = downloads.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Download not found")

    return job.as_dict()
