import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.music import lyrics, player, status_panel
from bot.music.player import is_authorized
from bot.music.queue import queues
from bot.music.youtube import Track


def _member(channel_id: int | None) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.voice = None if channel_id is None else SimpleNamespace(channel=SimpleNamespace(id=channel_id))
    return member


def _voice_client(channel_id: int) -> MagicMock:
    voice_client = MagicMock()
    voice_client.channel = SimpleNamespace(id=channel_id)
    return voice_client


def test_authorized_when_no_active_session():
    # No session yet - anyone can start one wherever they are.
    assert is_authorized(None, _member(channel_id=42)) is True


def test_authorized_when_member_in_same_channel():
    voice_client = _voice_client(channel_id=1)
    assert is_authorized(voice_client, _member(channel_id=1)) is True


def test_not_authorized_when_member_in_different_channel():
    voice_client = _voice_client(channel_id=1)
    assert is_authorized(voice_client, _member(channel_id=2)) is False


def test_not_authorized_when_member_not_in_any_voice_channel():
    voice_client = _voice_client(channel_id=1)
    assert is_authorized(voice_client, _member(channel_id=None)) is False


def test_not_authorized_when_not_a_guild_member():
    # e.g. a DM context where .voice doesn't exist at all.
    voice_client = _voice_client(channel_id=1)
    plain_user = MagicMock(spec=discord.User)
    assert is_authorized(voice_client, plain_user) is False


def setup_function() -> None:
    for task in player._idle_timers.values():
        task.cancel()
    player._idle_timers.clear()
    for task in player._lyric_tickers.values():
        task.cancel()
    player._lyric_tickers.clear()
    player._playback_positions.clear()
    status_panel._panels.clear()
    status_panel._current_lyric.clear()


async def test_ensure_voice_client_starts_idle_timer_before_posting_panel():
    # start_idle_timer must run before the (fallible) panel post, so the bot is never
    # left connected to voice with no cleanup timer if posting the panel goes wrong.
    guild_id = 301
    new_voice_client = MagicMock()
    new_voice_client.guild = SimpleNamespace(id=guild_id)

    channel = MagicMock()
    channel.connect = AsyncMock(return_value=new_voice_client)
    member = MagicMock(spec=discord.Member)
    member.voice = SimpleNamespace(channel=channel)

    interaction = MagicMock()
    interaction.guild = SimpleNamespace(voice_client=None, id=guild_id)
    interaction.user = member

    with patch.object(status_panel, "ensure_panel", new=AsyncMock(side_effect=RuntimeError("boom"))):
        try:
            await player.ensure_voice_client(interaction)
        except RuntimeError:
            pass

    assert guild_id in player._idle_timers
    player.cancel_idle_timer(guild_id)


async def test_cleanup_after_external_disconnect_clears_timer_and_panel():
    # Covers the case where the bot's voice connection ends without /leave or
    # the idle timeout ever running (kicked, moved, dropped connection) - the
    # panel/timer bookkeeping must not be left pointing at a dead session.
    guild_id = 303
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)

    with patch.object(player.settings, "idle_timeout_seconds", 10):
        player.start_idle_timer(voice_client)
    assert guild_id in player._idle_timers

    channel = MagicMock()
    channel.send = AsyncMock()
    panel_message = MagicMock()
    panel_message.channel = channel
    panel_message.delete = AsyncMock()
    status_panel._panels[guild_id] = panel_message

    await player.cleanup_after_external_disconnect(guild_id)

    assert guild_id not in player._idle_timers
    assert guild_id not in status_panel._panels
    panel_message.delete.assert_awaited_once()
    channel.send.assert_not_awaited()  # no reason message for an external disconnect


def test_playback_likely_failed_true_when_ffmpeg_raised_an_error():
    assert player._playback_likely_failed(RuntimeError("boom"), "") is True


def test_playback_likely_failed_false_for_clean_end_of_track():
    assert player._playback_likely_failed(None, "some harmless ffmpeg warning") is False


def test_playback_likely_failed_true_on_known_failure_signature():
    # Regression: this is the exact case that motivated the check -
    # discord.py's own error detection can race the ffmpeg process being
    # reaped and miss it, so a known-bad stderr signature is a backup net.
    stderr = "[https @ 0x...] HTTP error 403 Forbidden\nError opening input: Server returned 403 Forbidden"
    assert player._playback_likely_failed(None, stderr) is True


async def test_notify_playback_failed_posts_to_the_panel_channel():
    guild_id = 304
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    channel = MagicMock()
    channel.send = AsyncMock()
    panel_message = MagicMock()
    panel_message.channel = channel
    status_panel._panels[guild_id] = panel_message
    track = SimpleNamespace(title="Some Song")

    await player._notify_playback_failed(voice_client, track)

    channel.send.assert_awaited_once_with("Couldn't play **Some Song** - skipping.")


async def test_notify_playback_failed_is_a_noop_without_a_panel():
    guild_id = 305
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    track = SimpleNamespace(title="Some Song")

    await player._notify_playback_failed(voice_client, track)  # should not raise


def _track(title: str = "Song") -> Track:
    return Track(title=title, webpage_url="https://x/1", duration=200, uploader="Artist", requested_by="tester")


def test_playback_position_tracks_elapsed_time_across_pause_and_resume():
    guild_id = 401
    with patch("bot.music.player.time.monotonic", side_effect=[100.0, 105.0, 108.0, 115.0]):
        player._start_playback_position(guild_id)  # started_at = 100.0
        player._pause_playback_position(guild_id)  # paused_at = 105.0
        player._resume_playback_position(guild_id)  # accumulated_pause += 108 - 105 = 3.0
        elapsed = player._playback_positions[guild_id].elapsed()  # now = 115.0

    assert elapsed == 12.0  # (105-100) played + (115-108) played, 3s paused excluded


def test_playback_position_freezes_while_paused():
    guild_id = 402
    with patch("bot.music.player.time.monotonic", side_effect=[100.0, 106.0]):
        player._start_playback_position(guild_id)
        player._pause_playback_position(guild_id)

    # elapsed() while still paused must not advance further, and shouldn't
    # call time.monotonic() again (it isn't patched here anymore).
    assert player._playback_positions[guild_id].elapsed() == 6.0


async def test_pause_freezes_the_playback_position():
    guild_id = 403
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_playing.return_value = True
    player._playback_positions[guild_id] = player._PlaybackPosition(started_at=time.monotonic() - 5)

    with patch.object(status_panel, "refresh", new=AsyncMock()):
        await player.pause(voice_client)

    assert player._playback_positions[guild_id].paused_at is not None


async def test_resume_unfreezes_the_playback_position():
    guild_id = 404
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_paused.return_value = True
    position = player._PlaybackPosition(started_at=time.monotonic() - 5, paused_at=time.monotonic())
    player._playback_positions[guild_id] = position

    with patch.object(status_panel, "refresh", new=AsyncMock()):
        await player.resume(voice_client)

    assert position.paused_at is None


async def test_tick_lyrics_updates_the_panel_and_stops_once_the_track_changes():
    guild_id = 405
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_connected.return_value = True
    track = _track()
    queues.get(guild_id).now_playing = track
    player._playback_positions[guild_id] = player._PlaybackPosition(started_at=0.0)
    lines = [lyrics.LyricLine(seconds=0.0, text="Line 1")]

    call_count = 0

    async def fake_sleep(_seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            queues.get(guild_id).now_playing = None  # simulate the track ending

    with patch("bot.music.player.asyncio.sleep", side_effect=fake_sleep), \
         patch.object(status_panel, "update_lyric_line", new=AsyncMock()) as mock_update:
        await player._tick_lyrics(voice_client, track, lines)

    assert call_count == 2
    mock_update.assert_awaited_once_with(voice_client, "Line 1")


async def test_tick_lyrics_only_updates_the_panel_when_the_line_changes():
    guild_id = 406
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_connected.return_value = True
    track = _track()
    queues.get(guild_id).now_playing = track
    lines = [
        lyrics.LyricLine(seconds=0.0, text="Line 1"),
        lyrics.LyricLine(seconds=10.0, text="Line 2"),
    ]
    fake_position = MagicMock()
    fake_position.elapsed.side_effect = [1.0, 1.0, 11.0]
    player._playback_positions[guild_id] = fake_position

    call_count = 0

    async def fake_sleep(_seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 4:
            queues.get(guild_id).now_playing = None

    with patch("bot.music.player.asyncio.sleep", side_effect=fake_sleep), \
         patch.object(status_panel, "update_lyric_line", new=AsyncMock()) as mock_update:
        await player._tick_lyrics(voice_client, track, lines)

    assert mock_update.await_count == 2  # Line 1 once, Line 2 once - repeat of Line 1 skipped


async def test_load_lyrics_and_start_ticking_starts_a_ticker_when_lyrics_are_found():
    guild_id = 407
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    track = _track()
    queues.get(guild_id).now_playing = track
    found_lines = [lyrics.LyricLine(seconds=0.0, text="Line 1")]

    with patch.object(lyrics, "fetch_synced_lyrics", new=AsyncMock(return_value=found_lines)):
        await player._load_lyrics_and_start_ticking(voice_client, track)

    assert guild_id in player._lyric_tickers


async def test_load_lyrics_and_start_ticking_does_nothing_when_no_lyrics_found():
    guild_id = 408
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    track = _track()
    queues.get(guild_id).now_playing = track

    with patch.object(lyrics, "fetch_synced_lyrics", new=AsyncMock(return_value=None)):
        await player._load_lyrics_and_start_ticking(voice_client, track)

    assert guild_id not in player._lyric_tickers


async def test_load_lyrics_and_start_ticking_discards_stale_results():
    # If the track changed (skipped, ended) while the lyrics lookup was still
    # in flight, don't start a ticker showing lines for a track that's no
    # longer playing.
    guild_id = 409
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    track = _track()
    queues.get(guild_id).now_playing = track
    found_lines = [lyrics.LyricLine(seconds=0.0, text="Line 1")]

    async def fetch_side_effect(_requested_track):
        queues.get(guild_id).now_playing = _track("A different song")
        return found_lines

    with patch.object(lyrics, "fetch_synced_lyrics", new=AsyncMock(side_effect=fetch_side_effect)):
        await player._load_lyrics_and_start_ticking(voice_client, track)

    assert guild_id not in player._lyric_tickers


async def test_play_next_starts_a_lyrics_ticker_once_lyrics_are_found():
    guild_id = 410
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_connected.return_value = True
    queues.get(guild_id).add_priority(_track())
    found_lines = [lyrics.LyricLine(seconds=0.0, text="Line 1")]

    with patch.object(player, "resolve_stream_url", new=AsyncMock(return_value=("https://stream", "-vn"))), \
         patch("bot.music.player.discord.FFmpegPCMAudio", return_value=MagicMock()), \
         patch.object(lyrics, "fetch_synced_lyrics", new=AsyncMock(return_value=found_lines)), \
         patch.object(status_panel, "refresh", new=AsyncMock()):
        await player.play_next(voice_client)
        await asyncio.sleep(0)  # let the background lyrics-fetch task run

    assert guild_id in player._lyric_tickers
    assert guild_id in player._playback_positions


async def test_play_next_does_not_start_a_ticker_when_no_lyrics_are_found():
    guild_id = 411
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_connected.return_value = True
    queues.get(guild_id).add_priority(_track())

    with patch.object(player, "resolve_stream_url", new=AsyncMock(return_value=("https://stream", "-vn"))), \
         patch("bot.music.player.discord.FFmpegPCMAudio", return_value=MagicMock()), \
         patch.object(lyrics, "fetch_synced_lyrics", new=AsyncMock(return_value=None)), \
         patch.object(status_panel, "refresh", new=AsyncMock()):
        await player.play_next(voice_client)
        await asyncio.sleep(0)

    assert guild_id not in player._lyric_tickers


async def test_play_next_with_empty_queue_clears_lyric_ticker_and_position():
    guild_id = 412
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_connected.return_value = True
    player._lyric_tickers[guild_id] = asyncio.create_task(asyncio.sleep(10))
    player._playback_positions[guild_id] = player._PlaybackPosition(started_at=0.0)

    with patch.object(status_panel, "refresh", new=AsyncMock()):
        await player.play_next(voice_client)  # queue is empty

    assert guild_id not in player._lyric_tickers
    assert guild_id not in player._playback_positions


async def test_cleanup_after_external_disconnect_clears_lyric_ticker_and_position():
    guild_id = 413
    player._lyric_tickers[guild_id] = asyncio.create_task(asyncio.sleep(10))
    player._playback_positions[guild_id] = player._PlaybackPosition(started_at=0.0)

    await player.cleanup_after_external_disconnect(guild_id)

    assert guild_id not in player._lyric_tickers
    assert guild_id not in player._playback_positions
