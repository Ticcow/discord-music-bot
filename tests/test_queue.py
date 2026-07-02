from bot.music.queue import GuildQueue
from bot.music.youtube import Track


def _track(title: str) -> Track:
    return Track(
        title=title,
        webpage_url=f"https://example.com/{title}",
        duration=180,
        uploader=None,
        requested_by="tester",
    )


def test_priority_tracks_play_before_ambient_tracks():
    queue = GuildQueue()
    queue.add_ambient(_track("ambient-1"))
    queue.add_ambient(_track("ambient-2"))
    queue.add_priority(_track("priority-1"))

    assert queue.pop_next().title == "priority-1"
    assert queue.pop_next().title == "ambient-1"
    assert queue.pop_next().title == "ambient-2"
    assert queue.pop_next() is None


def test_play_leapfrogs_ahead_of_remaining_ambient_batch():
    # Simulates: /ask queues an ambient batch, one track starts playing, then
    # a /play request should jump ahead of the rest of that batch.
    queue = GuildQueue()
    queue.add_ambient(_track("kanye-1"))
    queue.add_ambient(_track("kanye-2"))
    queue.add_ambient(_track("kanye-3"))
    assert queue.pop_next().title == "kanye-1"

    queue.add_priority(_track("explicit-request"))

    assert queue.pop_next().title == "explicit-request"
    assert queue.pop_next().title == "kanye-2"
    assert queue.pop_next().title == "kanye-3"


def test_peek_all_lists_priority_before_ambient():
    queue = GuildQueue()
    queue.add_ambient(_track("ambient-1"))
    queue.add_priority(_track("priority-1"))

    assert [t.title for t in queue.peek_all()] == ["priority-1", "ambient-1"]
