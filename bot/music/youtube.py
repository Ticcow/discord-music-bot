import asyncio
from dataclasses import dataclass

import yt_dlp

_SEARCH_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
}

_RESOLVE_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
}

FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
)
FFMPEG_OPTIONS = "-vn"


@dataclass
class Track:
    title: str
    webpage_url: str
    duration: int | None
    uploader: str | None
    requested_by: str


def _search_sync(query: str) -> dict:
    with yt_dlp.YoutubeDL(_SEARCH_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ValueError(f"No results found for '{query}'")
            info = entries[0]
        return info


def _resolve_sync(webpage_url: str) -> str:
    with yt_dlp.YoutubeDL(_RESOLVE_OPTS) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
        return info["url"]


async def search(query: str, requested_by: str) -> Track:
    info = await asyncio.to_thread(_search_sync, query)
    return Track(
        title=info.get("title", query),
        webpage_url=info["webpage_url"],
        duration=info.get("duration"),
        uploader=info.get("uploader"),
        requested_by=requested_by,
    )


async def resolve_stream_url(track: Track) -> str:
    return await asyncio.to_thread(_resolve_sync, track.webpage_url)
