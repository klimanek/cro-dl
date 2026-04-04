import os
import asyncio
import aiohttp

from pathlib import Path

from crodl.tools.logger import crologger
from crodl.exceptions import DownloadError


async def download_part(
    url: str, session: aiohttp.ClientSession, target_folder: Path, semaphore: asyncio.Semaphore
):
    """Download a single part (segment / chunk) of an audio stream."""
    file_name = target_folder / os.path.basename(url)

    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(file_name, "wb") as f:
                        f.write(content)

                    crologger.info("Downloading %s... OK", url)
                else:
                    crologger.error("Downloading %s... Error", url)
                    raise DownloadError(
                        f"Error whiel downloading {url}: HTTP {response.status}"
                    )
        except asyncio.TimeoutError:
            crologger.error("Timeout while downloading %s", url)
            raise


async def download_parts(urls: list[str], target_folder: Path):
    """Download asynchronously audio parts (segments / chunks)."""
    os.makedirs(target_folder, exist_ok=True)  # Ensure the target folder exists
    semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent downloads

    async with aiohttp.ClientSession() as session:
        tasks = [download_part(url, session, target_folder, semaphore) for url in urls]
        await asyncio.gather(*tasks)
