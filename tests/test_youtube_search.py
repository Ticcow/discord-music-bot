import logging
from unittest.mock import MagicMock, patch

from bot.music.youtube import (
    _looks_like_music,
    _looks_like_youtube_url,
    _select_candidates,
    _track_from_info,
    search,
)


def _fake_ydl(extract_info_return: dict) -> MagicMock:
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.return_value = extract_info_return
    return ydl


def _entry(title="Song Title", uploader="Some Artist", duration=180, webpage_url="https://x/1"):
    return {"title": title, "uploader": uploader, "duration": duration, "webpage_url": webpage_url}


def test_looks_like_music_accepts_a_normal_length_track():
    assert _looks_like_music(_entry(duration=200)) is True


def test_looks_like_music_rejects_long_duration():
    assert _looks_like_music(_entry(duration=45 * 60)) is False


def test_looks_like_music_accepts_unknown_duration():
    # Some entries omit duration entirely; absence shouldn't be treated as "too long".
    assert _looks_like_music(_entry(duration=None)) is True


def test_looks_like_music_rejects_podcast_keyword_in_title():
    assert _looks_like_music(_entry(title="Kanye West Podcast Ep. 12")) is False


def test_looks_like_music_rejects_interview_keyword_in_uploader():
    assert _looks_like_music(_entry(uploader="Some Interview Show")) is False


def test_select_candidates_filters_out_non_music_entries():
    candidates = [
        _entry(title="Real Song", duration=180),
        _entry(title="Artist Podcast Special", duration=180),
        _entry(title="Another Real Song", duration=200),
    ]

    chosen = _select_candidates(candidates, count=5)

    titles = [c["title"] for c in chosen]
    assert titles == ["Real Song", "Another Real Song"]


def test_select_candidates_falls_back_to_all_when_nothing_passes_filter():
    # Regression: if every candidate happens to look like talk content
    # (e.g. an artist whose top hits are all long), still return something
    # rather than raising a false "no results".
    candidates = [
        _entry(title="Long Interview", duration=45 * 60),
        _entry(title="Another Long One", duration=50 * 60),
    ]

    chosen = _select_candidates(candidates, count=5)

    assert len(chosen) == 2


def test_select_candidates_prefers_topic_channels():
    candidates = [
        _entry(title="Song A", uploader="Some Channel"),
        _entry(title="Song B", uploader="Kanye West - Topic"),
    ]

    chosen = _select_candidates(candidates, count=5)

    assert chosen[0]["title"] == "Song B"


def test_select_candidates_respects_count():
    candidates = [_entry(title=f"Song {i}") for i in range(10)]

    chosen = _select_candidates(candidates, count=3)

    assert len(chosen) == 3


def test_track_from_info_uses_webpage_url_when_present():
    # Fully-resolved info dicts (e.g. from resolving a chosen track's stream).
    track = _track_from_info({"title": "Song", "webpage_url": "https://x/full"}, "tester")
    assert track.webpage_url == "https://x/full"


def test_track_from_info_falls_back_to_url_for_flat_extracted_entries():
    # Flat-extracted search candidates only have "url", not "webpage_url" -
    # regression guard since this silently KeyErrors if the fallback is lost.
    track = _track_from_info({"title": "Song", "url": "https://x/flat"}, "tester")
    assert track.webpage_url == "https://x/flat"


def test_looks_like_youtube_url_accepts_common_link_forms():
    assert _looks_like_youtube_url("https://www.youtube.com/watch?v=abc123") is True
    assert _looks_like_youtube_url("https://youtu.be/abc123") is True
    assert _looks_like_youtube_url("https://music.youtube.com/watch?v=abc123") is True
    assert _looks_like_youtube_url("https://m.youtube.com/watch?v=abc123") is True
    assert _looks_like_youtube_url("https://youtube.com/shorts/abc123") is True


def test_looks_like_youtube_url_rejects_plain_search_terms():
    assert _looks_like_youtube_url("early 2000s hip hop") is False
    assert _looks_like_youtube_url("kanye west") is False


async def test_search_resolves_a_direct_url_instead_of_searching_it():
    fake_info = {"title": "Direct Video", "url": "https://x/direct", "duration": 200}
    ydl = _fake_ydl(fake_info)

    with patch("bot.music.youtube.yt_dlp.YoutubeDL", return_value=ydl):
        track = await search("https://youtu.be/abc123", requested_by="tester")

    assert track.title == "Direct Video"
    ydl.extract_info.assert_called_once_with("https://youtu.be/abc123", download=False)


async def test_search_strips_discord_angle_bracket_wrapping():
    # Discord suppresses link previews for <url> - users often paste it that way.
    fake_info = {"title": "Direct Video", "url": "https://x/direct"}
    ydl = _fake_ydl(fake_info)

    with patch("bot.music.youtube.yt_dlp.YoutubeDL", return_value=ydl):
        track = await search("<https://youtu.be/abc123>", requested_by="tester")

    assert track.title == "Direct Video"
    ydl.extract_info.assert_called_once_with("https://youtu.be/abc123", download=False)


async def test_search_logs_the_query_and_the_picked_track(caplog):
    fake_entries = {"entries": [{"title": "Found Song", "url": "https://x/1"}]}
    ydl = _fake_ydl(fake_entries)

    with patch("bot.music.youtube.yt_dlp.YoutubeDL", return_value=ydl):
        with caplog.at_level(logging.INFO):
            track = await search("some query", requested_by="tester")

    assert track.title == "Found Song"
    assert "some query" in caplog.text
    assert "Found Song" in caplog.text
