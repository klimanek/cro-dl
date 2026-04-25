import aiohttp
from pathlib import Path
from typing import Optional

from crodl.tools.logger import crologger


async def download_image(url: str, target_path: Path) -> Optional[Path]:
    """
    Downloads an image from a URL and saves it to the target path.
    Used for thumbnails/covers of episodes and shows.
    
    Returns the path to the saved image or None if download failed.
    """
    crologger.info("Downloading image from: %s", url)
    
    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=30)
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Ensure the parent directory exists
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(target_path, "wb") as f:
                        f.write(content)
                    
                    crologger.info("Image saved to: %s", target_path)
                    return target_path
                else:
                    crologger.warning("Failed to download image: HTTP %s", response.status)
                    return None
    except Exception as e:
        crologger.error("Error during image download: %s", str(e))
        return None
