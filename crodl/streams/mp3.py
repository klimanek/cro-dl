from typing import Optional, Any
import aiohttp
from dataclasses import dataclass
from rich.progress import Progress

from crodl.streams.audioparts import AudioParts
from crodl.streams.utils import process_audiowork_title, shorten_title
from crodl.tools.logger import crologger


@dataclass
class MP3(AudioParts):
    """Process mp3 stream from CRo asynchronously."""

    async def download(self, progress: Optional[Progress] = None, task_id: Optional[Any] = None) -> None:
        """Download audiowork mp3 file asynchronously."""
        self._prepare_directories()

        file_url = self.url
        crologger.info("Downloading mp3: %s", file_url)

        async with aiohttp.ClientSession() as session:
            # For large files, we don't want a strict total timeout. 
            # We set a reasonable connect timeout and a longer sock_read timeout.
            timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=60)
            async with session.get(file_url, timeout=timeout) as resp:
                if resp.status != 200:
                    raise ValueError(f"Failed to download MP3: HTTP {resp.status}")

                content_length = resp.headers.get("Content-Length")
                total_length = int(content_length) if content_length else 0

                if not self.audiowork_dir:
                    raise ValueError("self.audiowork_dir is not set.")

                audio_full_path = (
                    self.audiowork_dir
                    / f"{process_audiowork_title(self.audio_title)}.mp3"
                )

                # Use external progress or create a new one
                if progress:
                    if task_id is None:
                        task_id = progress.add_task(
                            shorten_title(self.audio_title, 20), total=total_length
                        )
                    await self._download_to_file(resp, audio_full_path, progress, task_id)
                else:
                    with Progress() as internal_progress:
                        task_id = internal_progress.add_task(
                            shorten_title(self.audio_title, 20), total=total_length
                        )
                        await self._download_to_file(resp, audio_full_path, internal_progress, task_id)

        crologger.info("MP3 download completed: %s", audio_full_path)

    async def _download_to_file(self, resp, path, progress, task_id):
        """Internal helper to stream data to file and update progress."""
        with path.open("wb") as output:
            async for chunk in resp.content.iter_chunked(1024 * 64):
                output.write(chunk)
                progress.update(task_id, advance=len(chunk))
