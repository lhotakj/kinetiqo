import asyncio
import os
import time
from pathlib import Path

import httpx
from packaging.version import parse as parse_version

from kinetiqo.db.factory import get_version

CACHE_FILE = Path("latest_version.txt")
CACHE_DURATION = 3600  # 1 hour


async def get_latest_version():
    now = time.time()

    if CACHE_FILE.exists():
        try:
            mtime = os.path.getmtime(CACHE_FILE)
            if now - mtime < CACHE_DURATION:
                return CACHE_FILE.read_text().strip()
        except Exception as e:
            logger.warning(f"Failed to read cache file: {e}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.github.com/repos/lhotakj/kinetiqo/releases/latest")
            response.raise_for_status()
            latest_version = response.json()["tag_name"]

        CACHE_FILE.write_text(latest_version)
        return latest_version
    except (httpx.RequestError, KeyError) as e:
        logger.error(f"Failed to fetch latest version from GitHub: {e}")
        return None


async def check_for_new_version():
    current_version_str = get_version()
    
    # If we are in dev mode or version is not standard, we skip the check
    if not current_version_str or current_version_str.lower() == "dev":
        return None

    latest_version_str = await get_latest_version()
    
    if not latest_version_str:
        return None

    try:
        current_version = parse_version(current_version_str)
        latest_version = parse_version(latest_version_str)

        if latest_version > current_version:
            return f"New version {latest_version_str} available"
            
    except Exception as e:
        logger.warning(f"Version parsing failed: {e}")
        # Fallback to string inequality if parsing fails, but only if they are different
        if latest_version_str != current_version_str:
             # This is risky for semver but a reasonable fallback if parsing fails completely
             # However, given the requirement for strict checking, returning None might be safer 
             # if we can't parse it. But let's log it and return None to be safe.
             pass

    return None

if __name__ == '__main__':
    async def main():
        new_version_message = await check_for_new_version()
        if new_version_message:
            print(new_version_message)
        else:
            print("You are using the latest version.")

    asyncio.run(main())