"""Sound effects behind a swappable player.

Nothing here makes noise yet: the only implementation is
:class:`SilentPlayer`. Shipping the empty shell first is deliberate - the call
sites and the on/off switch exist now, so adding a real backend later is one
class and zero call-site churn. ``winsound`` (stdlib; WAV only, no volume, no
stop), ``pygame.mixer`` and a file-based player all fit this protocol.

Keys are **semantic** (``feed`` / ``level_up``), never file names: the mapping
from key to file belongs to whichever backend eventually lands, and that keeps
an asset reshuffle from touching game logic.
"""

from __future__ import annotations

from typing import Protocol

__all__ = [
    "SOUND_KEYS",
    "SilentPlayer",
    "SoundPlayer",
    "sound_for_group",
    "sound_for_refusal",
]


# Every event that is allowed to make a sound. Keeping the list closed means a
# typo in a call site is caught by a test rather than silently playing nothing.
SOUND_KEYS: tuple[str, ...] = (
    "click",  # the user poked the pet
    "wave",  # hover greeting
    "feed",  # an item from the 喂食 group landed
    "play",  # 玩耍 group
    "rest",  # 休息 group
    "refuse",  # the pet said no (full / daily limit / cooldown)
    "level_up",  # affection crossed a threshold
    "land",  # finished a fall
    "perch",  # jumped onto a window
)

_GROUP_KEYS = {"feed": "feed", "play": "play", "rest": "rest"}


class SoundPlayer(Protocol):
    """Plays a short effect for a semantic key. Must never block the UI."""

    def play(self, key: str) -> None: ...


class SilentPlayer:
    """Default player: records what *would* have played and stays quiet.

    The recording is what makes it useful - tests assert the right event fired
    without anyone having to hear it.
    """

    def __init__(self, max_history: int = 32) -> None:
        self.max_history = max_history
        self.history: list[str] = []

    def play(self, key: str) -> None:
        self.history.append(key)
        if len(self.history) > self.max_history:
            del self.history[: len(self.history) - self.max_history]

    @property
    def last(self) -> str | None:
        return self.history[-1] if self.history else None

    def clear(self) -> None:
        self.history.clear()


def sound_for_group(group: str | None) -> str | None:
    """Map an item group (``feed`` / ``play`` / ``rest``) to its sound key."""
    return _GROUP_KEYS.get(group or "")


def sound_for_refusal() -> str:
    """All three refusals share one sound; they are distinguished by dialogue."""
    return "refuse"
