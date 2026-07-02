import asyncio
import logging
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

logger = logging.getLogger(__name__)


def installed_version() -> str | None:
    try:
        return _pkg_version("yt-dlp")
    except PackageNotFoundError:
        return None


async def update_yt_dlp() -> tuple[str | None, str | None]:
    """Runs `pip install --upgrade yt-dlp` in this venv (sys.executable, so it
    targets whichever venv the bot itself is running in). Returns (version
    before, version after) - equal if nothing changed, whether that's because
    it was already current or because the upgrade attempt itself failed
    (logged either way, not raised - callers treat this as "no update happened")."""
    before = installed_version()
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error("yt-dlp upgrade failed: %s", stderr.decode(errors="replace").strip())
        return before, before

    after = installed_version()
    if after != before:
        logger.info("yt-dlp upgraded %s -> %s", before, after)
    return before, after
