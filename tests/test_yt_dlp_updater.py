from unittest.mock import AsyncMock, MagicMock, patch

from bot.music import yt_dlp_updater


def _fake_process(returncode: int, stderr: bytes = b"") -> MagicMock:
    process = MagicMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(b"", stderr))
    return process


async def test_update_yt_dlp_reports_the_version_change():
    with patch.object(yt_dlp_updater, "installed_version", side_effect=["2026.6.9", "2026.7.1"]), \
         patch("bot.music.yt_dlp_updater.asyncio.create_subprocess_exec", new=AsyncMock(return_value=_fake_process(0))):
        before, after = await yt_dlp_updater.update_yt_dlp()

    assert before == "2026.6.9"
    assert after == "2026.7.1"


async def test_update_yt_dlp_reports_no_change_when_already_current():
    with patch.object(yt_dlp_updater, "installed_version", side_effect=["2026.6.9", "2026.6.9"]), \
         patch("bot.music.yt_dlp_updater.asyncio.create_subprocess_exec", new=AsyncMock(return_value=_fake_process(0))):
        before, after = await yt_dlp_updater.update_yt_dlp()

    assert before == after == "2026.6.9"


async def test_update_yt_dlp_reports_no_change_when_pip_fails():
    # A failed upgrade attempt must not be mistaken for "nothing to update" -
    # but it also shouldn't raise and take the caller down with it.
    with patch.object(yt_dlp_updater, "installed_version", return_value="2026.6.9"), \
         patch(
             "bot.music.yt_dlp_updater.asyncio.create_subprocess_exec",
             new=AsyncMock(return_value=_fake_process(1, stderr=b"network unreachable")),
         ):
        before, after = await yt_dlp_updater.update_yt_dlp()

    assert before == after == "2026.6.9"
