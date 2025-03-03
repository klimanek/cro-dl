import os
import asyncio
import aiohttp

from pathlib import Path

from crodl.tools.logger import crologger
from crodl.exceptions import DownloadError


async def download_part(url: str, session: aiohttp.ClientSession, target_folder: Path):
    """Download a single part (segment / chunk) of an audio stream."""
    file_name = target_folder / os.path.basename(url)

    async with session.get(url) as response:
        if response.status == 200:
            with open(file_name, "wb") as f:
                content = await response.content.read()
                f.write(content)

            crologger.info("Downloading %s... OK", url)
        else:
            crologger.error("Downloading %s... Error", url)
            raise DownloadError(
                f"Error whiel downloading {url}: HTTP {response.status}"
            )


async def download_parts(urls: list[str], target_folder: Path):
    """Download asynchronously audio parts (segments / chunks)."""
    os.makedirs(target_folder, exist_ok=True)  # Ensure the target folder exists

    async with aiohttp.ClientSession() as session:
        tasks = [download_part(url, session, target_folder) for url in urls]
        await asyncio.gather(*tasks)
