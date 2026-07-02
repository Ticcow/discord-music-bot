from bot.main import MusicBot


async def test_bot_blocks_everyone_and_user_mentions_but_keeps_reply_pings():
    # Track titles come from YouTube video metadata, which is entirely
    # attacker-controlled (anyone can upload a video titled "<@some_user_id>"),
    # and get echoed into plain message content in /queue, /play, and /ask
    # replies. A malicious title must never turn into a real ping - but replying
    # to a user's @mention chat message should still notify them as normal.
    bot = MusicBot()

    assert bot.allowed_mentions.everyone is False
    assert bot.allowed_mentions.users is False
    assert bot.allowed_mentions.roles is False
    assert bot.allowed_mentions.replied_user is True
