from collections import deque

from bot.music.youtube import Track


class GuildQueue:
    """Two lanes: priority (explicit /play requests) always plays before
    ambient (batches auto-queued by the natural-language agent), so a /play
    request leapfrogs whatever ambient tracks are still queued."""

    def __init__(self) -> None:
        self._priority: deque[Track] = deque()
        self._ambient: deque[Track] = deque()
        self.now_playing: Track | None = None

    def add_priority(self, track: Track) -> None:
        self._priority.append(track)

    def add_ambient(self, track: Track) -> None:
        self._ambient.append(track)

    def pop_next(self) -> Track | None:
        if self._priority:
            self.now_playing = self._priority.popleft()
        elif self._ambient:
            self.now_playing = self._ambient.popleft()
        else:
            self.now_playing = None
        return self.now_playing

    def peek_all(self) -> list[Track]:
        return list(self._priority) + list(self._ambient)

    def clear(self) -> None:
        self._priority.clear()
        self._ambient.clear()
        self.now_playing = None

    def is_empty(self) -> bool:
        return not self._priority and not self._ambient


class QueueManager:
    def __init__(self) -> None:
        self._queues: dict[int, GuildQueue] = {}

    def get(self, guild_id: int) -> GuildQueue:
        if guild_id not in self._queues:
            self._queues[guild_id] = GuildQueue()
        return self._queues[guild_id]


queues = QueueManager()
