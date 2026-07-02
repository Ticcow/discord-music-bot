from collections import deque

from bot.music.youtube import Track


class GuildQueue:
    def __init__(self) -> None:
        self._tracks: deque[Track] = deque()
        self.now_playing: Track | None = None

    def add(self, track: Track) -> None:
        self._tracks.append(track)

    def pop_next(self) -> Track | None:
        self.now_playing = self._tracks.popleft() if self._tracks else None
        return self.now_playing

    def peek_all(self) -> list[Track]:
        return list(self._tracks)

    def clear(self) -> None:
        self._tracks.clear()
        self.now_playing = None

    def is_empty(self) -> bool:
        return not self._tracks


class QueueManager:
    def __init__(self) -> None:
        self._queues: dict[int, GuildQueue] = {}

    def get(self, guild_id: int) -> GuildQueue:
        if guild_id not in self._queues:
            self._queues[guild_id] = GuildQueue()
        return self._queues[guild_id]


queues = QueueManager()
