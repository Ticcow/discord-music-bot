import asyncio
import logging
import re
from dataclasses import dataclass

import aiohttp

from bot.music.youtube import Track

logger = logging.getLogger(__name__)

_LRCLIB_GET_URL = "https://lrclib.net/api/get"
_LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)

_LRC_LINE_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")

# YouTube titles pile on noise ("(Official Video)", "(Official Audio) ft. X",
# "(Remastered)") that a plain LRCLIB lookup won't match against - strip any
# bracketed chunk containing one of these keywords, regardless of what else
# is bracketed alongside it.
_TITLE_NOISE_RE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(official|video|audio|lyrics?|visualizer|hd|4k|remaster\w*)\b[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
# Splits "Artist - Title" / "Artist – Title" on a hyphen or any unicode dash.
_DASH_SPLIT_RE = re.compile(r"\s+[-‐-―]\s+")


@dataclass(frozen=True)
class LyricLine:
    seconds: float
    text: str


def _guess_artist_and_title(track: Track) -> tuple[str, str]:
    """yt-dlp's title/uploader are messy real-world strings, not clean tags.
    The channel name (uploader) is often a "- Topic" auto-channel or a VEVO/
    label handle, while a "Artist - Title" pattern embedded in the video
    title itself tends to be the more reliable artist credit when present."""
    uploader_artist = (track.uploader or "").strip()
    if uploader_artist.lower().endswith("- topic"):
        uploader_artist = uploader_artist[: -len("- topic")].strip()

    title = _TITLE_NOISE_RE.sub("", track.title).strip()
    parts = _DASH_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        title_artist, title = parts[0].strip(), parts[1].strip()
        artist = title_artist or uploader_artist
    else:
        artist = uploader_artist

    return artist, title


def _parse_lrc(lrc_text: str) -> list[LyricLine]:
    lines = []
    for raw_line in lrc_text.splitlines():
        match = _LRC_LINE_RE.match(raw_line)
        if not match:
            continue
        minutes, seconds, text = match.groups()
        text = text.strip()
        if not text:
            continue
        lines.append(LyricLine(seconds=int(minutes) * 60 + float(seconds), text=text))
    lines.sort(key=lambda line: line.seconds)
    return lines


async def _lookup_synced_lyrics(
    session: aiohttp.ClientSession, artist: str, title: str, duration: float | None
) -> str | None:
    params = {"track_name": title, "artist_name": artist}
    if duration:
        params["duration"] = str(round(duration))
    async with session.get(_LRCLIB_GET_URL, params=params) as resp:
        if resp.status == 200:
            data = await resp.json()
            if data.get("syncedLyrics"):
                return data["syncedLyrics"]

    # Exact lookup failed (mismatched tags, wrong duration, etc.) - fall back
    # to fuzzy search and take the first result that actually has sync data.
    async with session.get(_LRCLIB_SEARCH_URL, params={"q": f"{artist} {title}"}) as resp:
        if resp.status != 200:
            return None
        for result in await resp.json():
            if result.get("syncedLyrics"):
                return result["syncedLyrics"]
    return None


async def fetch_synced_lyrics(track: Track) -> list[LyricLine] | None:
    """Best-effort lookup of time-synced lyrics for a track via LRCLIB.
    Returns None if no match is found, the track has no lyrics (e.g. an
    instrumental), or the request fails - callers should treat a None as
    "not available for this track", not an error."""
    artist, title = _guess_artist_and_title(track)
    if not title:
        return None

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            synced_text = await _lookup_synced_lyrics(session, artist, title, track.duration)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.warning("Lyrics lookup failed for %r", track.title)
        return None

    if not synced_text:
        return None
    return _parse_lrc(synced_text) or None


def current_line(lines: list[LyricLine], elapsed_seconds: float) -> LyricLine | None:
    """The last line whose timestamp has passed, or None before the first line."""
    current = None
    for line in lines:
        if line.seconds > elapsed_seconds:
            break
        current = line
    return current
