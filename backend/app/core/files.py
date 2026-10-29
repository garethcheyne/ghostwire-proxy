"""File reads and writes for async code.

The API runs as one uvicorn worker, so a blocking call in a request handler stalls
every other request. These helpers do the disk work in a thread.
"""

import asyncio
import os


def _read_text(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write_text(path: str, text: str, private: bool) -> None:
    if not private:
        with open(path, "w") as f:
            f.write(text)
        return
    # Created owner-only from the start, so a private key is never briefly readable
    # by others; chmod covers a file that already existed with wider permissions.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        os.chmod(path, 0o600)
        f.write(text)


def _remove_file(path: str) -> bool:
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


async def read_text(path: str) -> str | None:
    """The file's text (newlines as stored), or None if it isn't a regular file."""
    return await asyncio.to_thread(_read_text, path)


async def write_text(path: str, text: str, *, private: bool = False) -> None:
    """Write text to path, replacing it. private=True makes the file mode 0600."""
    await asyncio.to_thread(_write_text, path, text, private)


async def remove_file(path: str) -> bool:
    """Delete path if it exists; True if it did."""
    return await asyncio.to_thread(_remove_file, path)
