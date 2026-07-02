from bot.music.youtube import _looks_like_music, _select_candidates, _track_from_info


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
