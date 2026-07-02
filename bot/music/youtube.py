import asyncio
import logging
import re
import shlex
from dataclasses import dataclass

import yt_dlp

logger = logging.getLogger(__name__)

_BASE_OPTS = {
    "format": "bestaudio[acodec=opus]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "remote_components": ["ejs:github"],
}

# Candidate search only needs title/duration/uploader to filter and pick a
# winner, not a fully resolved stream - extract_flat skips the expensive
# per-video page/player extraction (~6x faster for a handful of candidates)
# and still exposes the fields the music filter needs.
_SEARCH_OPTS = {**_BASE_OPTS, "extract_flat": True}

_YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.|music\.|m\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)",
    re.IGNORECASE,
)

_FFMPEG_RECONNECT_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


@dataclass
class Track:
    title: str
    webpage_url: str
    duration: int | None
    uploader: str | None
    requested_by: str


def _track_from_info(info: dict, requested_by: str) -> Track:
    # Flat-extracted search results only have "url"; fully-resolved info
    # dicts have "webpage_url". Accept either.
    return Track(
        title=info.get("title", "Unknown title"),
        webpage_url=info.get("webpage_url") or info["url"],
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
    with yt_dlp.YoutubeDL(_SEARCH_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch{candidate_count}:{query}", download=False)
        candidates = [e for e in info.get("entries", []) if e]
        if not candidates:
            raise ValueError(f"No results found for '{query}'")
        return _select_candidates(candidates, count)


def _looks_like_youtube_url(query: str) -> bool:
    return bool(_YOUTUBE_URL_RE.match(query))


def _lookup_url_sync(url: str) -> dict:
    # Flat extraction here mirrors _search_sync's candidate lookup: cheap
    # metadata only (title/duration/uploader), no stream resolution. The
    # actual stream URL is still resolved lazily at play time.
    with yt_dlp.YoutubeDL(_SEARCH_OPTS) as ydl:
        return ydl.extract_info(url, download=False)


def _build_before_options(http_headers: dict) -> str:
    # YouTube's CDN increasingly rejects a stream request that doesn't carry
    # the same headers (e.g. User-Agent) yt-dlp used to resolve the URL,
    # returning a 403 with no audio and no visible error. shlex.quote keeps
    # the \r\n-joined header block intact as a single ffmpeg argument once
    # discord.py re-splits this string with shlex.split.
    options = _FFMPEG_RECONNECT_OPTIONS
    if http_headers:
        header_str = "".join(f"{k}: {v}\r\n" for k, v in http_headers.items())
        options += f" -headers {shlex.quote(header_str)}"
    return options


def _resolve_sync(webpage_url: str) -> tuple[str, str, str | None]:
    with yt_dlp.YoutubeDL(_BASE_OPTS) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
        before_options = _build_before_options(info.get("http_headers") or {})
        return info["url"], before_options, info.get("acodec")


async def search(query: str, requested_by: str) -> Track:
    query = query.strip()
    if query.startswith("<") and query.endswith(">"):
        query = query[1:-1]

    if _looks_like_youtube_url(query):
        info = await asyncio.to_thread(_lookup_url_sync, query)
        track = _track_from_info(info, requested_by)
    else:
        entries = await asyncio.to_thread(_search_sync, query, 1)
        track = _track_from_info(entries[0], requested_by)

    logger.info("search %r -> %r", query, track.title)
    return track


async def search_many(query: str, count: int, requested_by: str) -> list[Track]:
    entries = await asyncio.to_thread(_search_sync, query, count)
    tracks = [_track_from_info(entry, requested_by) for entry in entries]
    logger.info("search %r -> %s", query, [t.title for t in tracks])
    return tracks


async def resolve_stream_url(track: Track) -> tuple[str, str, str | None]:
    """Returns (direct stream URL, ffmpeg before_options, source audio codec).
    before_options carries yt-dlp's http_headers - see _build_before_options for why
    that's required. The codec (e.g. "opus", "mp4a.40.2") lets the caller decide
    whether ffmpeg can remux the stream as-is or must transcode it."""
    return await asyncio.to_thread(_resolve_sync, track.webpage_url)
