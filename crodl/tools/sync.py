import os
import hashlib
from pathlib import Path
from typing import Dict, Optional
from crodl.persistence.repository import LibraryRepository
from crodl.persistence.models import Episode
from crodl.settings import DOWNLOAD_PATH, AUDIO_FORMATS
from crodl.tools.logger import crologger

class LibrarySync:
    """Simple manager for syncing disk files to the database."""

    def __init__(self):
        self.repo = LibraryRepository()

    async def sync_all(self) -> Dict[str, int]:
        """Scans DOWNLOAD_PATH and ensures every audio file is in the DB."""
        crologger.info("Starting simple library sync...")
        
        audio_files = []
        for root, _, files in os.walk(DOWNLOAD_PATH):
            if ".chunks" in root: continue
            for file in files:
                if file.lower().endswith(AUDIO_FORMATS):
                    audio_files.append(Path(root) / file)

        results = {"success": 0, "failed": 0}
        
        for audio_path in audio_files:
            try:
                # Generate unique ID based on full path
                local_id = hashlib.sha256(str(audio_path).encode()).hexdigest()[:16]
                
                # Always create/update basic entry
                episode = Episode(
                    id=local_id,
                    title=audio_path.stem,
                    local_path=str(audio_path),
                    audio_format=audio_path.suffix.lstrip("."),
                    is_manual=True
                )
                await self.repo.save_episode(episode)
                results["success"] += 1
                crologger.info("Synced: %s", audio_path.name)
            except Exception as e:
                crologger.error("Sync failed for %s: %s", audio_path.name, str(e))
                results["failed"] += 1
                
        return results
