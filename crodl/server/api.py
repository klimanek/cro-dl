from typing import List, Sequence
from fastapi import APIRouter, HTTPException, Depends
from crodl.persistence.repository import LibraryRepository
from crodl.persistence.models import Episode, Show, Series

router = APIRouter()

# Dependency to get the repository
async def get_repo():
    return LibraryRepository()

@router.get("/episodes", response_model=List[Episode])
async def list_episodes(repo: LibraryRepository = Depends(get_repo)):
    """Returns a list of all downloaded episodes."""
    return await repo.get_all_episodes()

@router.get("/episodes/{uuid}", response_model=Episode)
async def get_episode(uuid: str, repo: LibraryRepository = Depends(get_repo)):
    """Returns details of a specific episode."""
    episode = await repo.get_episode(uuid)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode

@router.get("/library-stats")
async def get_stats(repo: LibraryRepository = Depends(get_repo)):
    """Returns basic statistics about the local library."""
    episodes = await repo.get_all_episodes()
    return {
        "total_episodes": len(episodes),
        "total_shows": len(set(e.show_id for e in episodes if e.show_id)),
        "total_series": len(set(e.series_id for e in episodes if e.series_id))
    }
