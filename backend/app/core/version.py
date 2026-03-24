"""Application version reader — safe to import from any module (no circular deps)."""

import os
from pathlib import Path


def get_app_version() -> str:
    """Read application version from VERSION file."""
    for candidate in [
        Path("/app/VERSION"),                            # Docker volume mount
        Path(__file__).parent.parent.parent / "VERSION", # Local dev (backend/)
        Path(__file__).parent.parent.parent.parent / "VERSION",  # Project root
    ]:
        try:
            if candidate.exists():
                return candidate.read_text().strip()
        except Exception:
            continue
    return os.environ.get("APP_VERSION", "0.0.0")


APP_VERSION = get_app_version()
