import asyncio
from dataclasses import dataclass

import yt_dlp

_BASE_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "remote_components": ["ejs:github"],
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


def _track_from_info(info: dict, requested_by: str) -> Track:
    return Track(
        title=info.get("title", "Unknown title"),
        webpage_url=info["webpage_url"],
        duration=info.get("duration"),
        uploader=info.get("uploader"),
        requested_by=requested_by,
    )


# Plain YouTube search for an artist/song name happily surfaces podcasts,
# interviews, and reaction videos alongside actual tracks. There's no
# reliable "music only" search scope in this yt-dlp version, so instead
# fetch a wider candidate pool and filter out results that look like talk
# content: songs are almost always under 10 minutes, and podcast/interview/
# reaction uploads tend to say so in the title or channel name.
_MAX_MUSIC_DURATION_SECONDS = 10 * 60
_NON_MUSIC_KEYWORDS = (
    "podcast",
    "interview",
    "reaction",
    "full episode",
    "breakdown",
    "review",
    "documentary",
)


def _looks_like_music(entry: dict) -> bool:
    title = (entry.get("title") or "").lower()
    uploader = (entry.get("uploader") or "").lower()
    duration = entry.get("duration")
    if any(keyword in title or keyword in uploader for keyword in _NON_MUSIC_KEYWORDS):
        return False
    if duration is not None and duration > _MAX_MUSIC_DURATION_SECONDS:
        return False
    return True


def _select_candidates(candidates: list[dict], count: int) -> list[dict]:
    music = [e for e in candidates if _looks_like_music(e)]
    # If nothing passes the filter, prefer surfacing something over a false
    # "no results" - better to occasionally play a borderline result than to
    # fail outright on artists/queries the heuristic doesn't recognize.
    chosen = list(music if music else candidates)
    # Prefer official artist "Topic" channels (YouTube's auto-generated,
    # music-only channels) when available, otherwise keep search order.
    chosen.sort(key=lambda e: 0 if (e.get("uploader") or "").lower().endswith("topic") else 1)
    return chosen[:count]


def _search_sync(query: str, count: int) -> list[dict]:
    candidate_count = max(count * 4, 8)
    with yt_dlp.YoutubeDL(_BASE_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch{candidate_count}:{query}", download=False)
        candidates = [e for e in info.get("entries", []) if e]
        if not candidates:
            raise ValueError(f"No results found for '{query}'")
        return _select_candidates(candidates, count)


def _resolve_sync(webpage_url: str) -> str:
    with yt_dlp.YoutubeDL(_BASE_OPTS) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
        return info["url"]


async def search(query: str, requested_by: str) -> Track:
    entries = await asyncio.to_thread(_search_sync, query, 1)
    return _track_from_info(entries[0], requested_by)


async def search_many(query: str, count: int, requested_by: str) -> list[Track]:
    entries = await asyncio.to_thread(_search_sync, query, count)
    return [_track_from_info(entry, requested_by) for entry in entries]


async def resolve_stream_url(track: Track) -> str:
    return await asyncio.to_thread(_resolve_sync, track.webpage_url)
