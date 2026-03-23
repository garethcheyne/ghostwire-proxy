"""GeoIP database update service.

Downloads the free DB-IP Country Lite database (updated monthly).
The database is compatible with MaxMindDB format used by lua-resty-maxminddb.
"""

import gzip
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

GEOIP_DIR = Path("/data/geoip")
DB_FILENAME = "GeoLite2-Country.mmdb"
DB_PATH = GEOIP_DIR / DB_FILENAME
TEMP_PATH = GEOIP_DIR / f"{DB_FILENAME}.tmp"

# DB-IP free country lite database (updated on 1st of each month)
DBIP_URL_TEMPLATE = "https://download.db-ip.com/free/dbip-country-lite-{year}-{month:02d}.mmdb.gz"


def _get_download_url() -> str:
    """Get the download URL for the current month's database."""
    now = datetime.now(timezone.utc)
    return DBIP_URL_TEMPLATE.format(year=now.year, month=now.month)


def get_db_info() -> dict:
    """Get info about the currently installed GeoIP database."""
    if not DB_PATH.exists():
        return {
            "installed": False,
            "path": str(DB_PATH),
            "size_bytes": 0,
            "last_modified": None,
        }

    stat = DB_PATH.stat()
    return {
        "installed": True,
        "path": str(DB_PATH),
        "size_bytes": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


async def update_database() -> dict:
    """Download and install the latest GeoIP database.

    Returns a dict with status information about the update.
    """
    GEOIP_DIR.mkdir(parents=True, exist_ok=True)

    url = _get_download_url()
    logger.info(f"Downloading GeoIP database from {url}")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Decompress gzip and write to temp file
            with open(TEMP_PATH, "wb") as f:
                f.write(gzip.decompress(response.content))

            # Verify the file is a valid MMDB (starts with specific metadata)
            with open(TEMP_PATH, "rb") as f:
                # MMDB files contain the metadata marker near the end
                content = f.read()
                if b"\xab\xcd\xefMaxMind.com" not in content:
                    TEMP_PATH.unlink(missing_ok=True)
                    raise ValueError("Downloaded file is not a valid MaxMindDB database")

            # Atomic replace
            shutil.move(str(TEMP_PATH), str(DB_PATH))

            info = get_db_info()
            logger.info(f"GeoIP database updated successfully ({info['size_bytes']} bytes)")

            return {
                "status": "success",
                "message": "GeoIP database updated successfully",
                "source": url,
                **info,
            }

    except httpx.HTTPStatusError as e:
        TEMP_PATH.unlink(missing_ok=True)
        msg = f"Failed to download GeoIP database: HTTP {e.response.status_code}"
        logger.error(msg)
        return {"status": "error", "message": msg}
    except Exception as e:
        TEMP_PATH.unlink(missing_ok=True)
        msg = f"Failed to update GeoIP database: {e}"
        logger.error(msg)
        return {"status": "error", "message": msg}
