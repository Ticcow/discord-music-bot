from unittest.mock import MagicMock, patch

import aiohttp

from bot.music.lyrics import (
    LyricLine,
    _guess_artist_and_title,
    _parse_lrc,
    current_line,
    fetch_synced_lyrics,
)
from bot.music.youtube import Track


def _track(title: str, uploader: str | None = None, duration: float | None = 200) -> Track:
    return Track(
        title=title, webpage_url="https://x/1", duration=duration, uploader=uploader,
        requested_by="tester",
    )


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.requested_urls: list[str] = []

    def get(self, url, params=None):
        self.requested_urls.append(url)
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _RaisingSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, params=None):
        raise aiohttp.ClientError("boom")


def test_parse_lrc_extracts_timestamps_and_text():
    lrc = "[00:01.50]First line\n[00:12.00]Second line"
    lines = _parse_lrc(lrc)
    assert lines == [LyricLine(seconds=1.5, text="First line"), LyricLine(seconds=12.0, text="Second line")]


def test_parse_lrc_ignores_metadata_and_blank_lines():
    lrc = "[ar:Some Artist]\n[00:01.00]Real line\n[00:02.00]   \n"
    lines = _parse_lrc(lrc)
    assert lines == [LyricLine(seconds=1.0, text="Real line")]


def test_parse_lrc_sorts_by_timestamp_even_if_file_is_out_of_order():
    lrc = "[00:10.00]Later\n[00:01.00]Earlier"
    lines = _parse_lrc(lrc)
    assert [line.text for line in lines] == ["Earlier", "Later"]


def test_guess_artist_and_title_prefers_title_embedded_artist_over_uploader():
    # Regression: the uploader/channel name ("Queen Official") is often a
    # VEVO/label handle, while "Artist - Title" in the video title itself is
    # usually the more reliable credit for matching against LRCLIB.
    artist, title = _guess_artist_and_title(
        _track("Queen – Bohemian Rhapsody (Official Video Remastered)", uploader="Queen Official")
    )
    assert artist == "Queen"
    assert title == "Bohemian Rhapsody"


def test_guess_artist_and_title_strips_topic_suffix_from_uploader():
    artist, title = _guess_artist_and_title(_track("aruarian dance", uploader="Nujabes - Topic"))
    assert artist == "Nujabes"
    assert title == "aruarian dance"


def test_guess_artist_and_title_falls_back_to_uploader_when_title_has_no_dash():
    artist, title = _guess_artist_and_title(_track("SICKO MODE (Official Video)", uploader="Travis Scott"))
    assert artist == "Travis Scott"
    assert title == "SICKO MODE"


def test_current_line_is_none_before_the_first_line():
    lines = [LyricLine(seconds=5.0, text="First")]
    assert current_line(lines, elapsed_seconds=2.0) is None


def test_current_line_returns_the_latest_line_that_has_passed():
    lines = [
        LyricLine(seconds=1.0, text="First"),
        LyricLine(seconds=10.0, text="Second"),
        LyricLine(seconds=20.0, text="Third"),
    ]
    assert current_line(lines, elapsed_seconds=15.0).text == "Second"


async def test_fetch_synced_lyrics_returns_lines_on_exact_match():
    session = _FakeSession([_FakeResponse(200, {"syncedLyrics": "[00:01.00]Hello"})])
    with patch("bot.music.lyrics.aiohttp.ClientSession", return_value=session):
        lines = await fetch_synced_lyrics(_track("Artist - Title", uploader="Artist"))

    assert lines == [LyricLine(seconds=1.0, text="Hello")]
    assert session.requested_urls == ["https://lrclib.net/api/get"]


async def test_fetch_synced_lyrics_falls_back_to_search_when_exact_lookup_misses():
    session = _FakeSession([
        _FakeResponse(404, {}),
        _FakeResponse(200, [{"syncedLyrics": None}, {"syncedLyrics": "[00:05.00]Found via search"}]),
    ])
    with patch("bot.music.lyrics.aiohttp.ClientSession", return_value=session):
        lines = await fetch_synced_lyrics(_track("Artist - Title", uploader="Artist"))

    assert lines == [LyricLine(seconds=5.0, text="Found via search")]
    assert session.requested_urls == ["https://lrclib.net/api/get", "https://lrclib.net/api/search"]


async def test_fetch_synced_lyrics_returns_none_when_nothing_matches():
    session = _FakeSession([_FakeResponse(404, {}), _FakeResponse(200, [])])
    with patch("bot.music.lyrics.aiohttp.ClientSession", return_value=session):
        lines = await fetch_synced_lyrics(_track("Artist - Title", uploader="Artist"))

    assert lines is None


async def test_fetch_synced_lyrics_returns_none_on_network_error():
    with patch("bot.music.lyrics.aiohttp.ClientSession", return_value=_RaisingSession()):
        lines = await fetch_synced_lyrics(_track("Artist - Title", uploader="Artist"))

    assert lines is None


async def test_fetch_synced_lyrics_skips_the_network_call_for_an_unusable_title():
    # A title that's entirely noise (e.g. a bare "(Official Video)" upload
    # with no real title text) leaves nothing to search for.
    always_fails = MagicMock(side_effect=AssertionError("should not open a session"))
    with patch("bot.music.lyrics.aiohttp.ClientSession", always_fails):
        lines = await fetch_synced_lyrics(_track("(Official Video)", uploader=None))

    assert lines is None
