"""Sound effects behind a swappable player.

Two implementations live here: :class:`SilentPlayer` (records what *would*
play; the default and the non-Windows fallback) and :class:`WinsoundPlayer`
(Windows stdlib ``winsound``, WAV files under ``assets/sounds/``). The call
sites and the on/off switch predate both, so a backend swap never touches game
logic. Keys are **semantic** (``feed`` / ``level_up``), never file names: the
key-to-file mapping belongs to the backend, which keeps an asset reshuffle
from touching call sites.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

__all__ = [
    "SOUND_KEYS",
    "SilentPlayer",
    "SoundPlayer",
    "WinsoundPlayer",
    "make_sound_player",
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
    "focus_start",  # a focus stretch began
    "focus_done",  # a focus stretch finished
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


class WinsoundPlayer:
    """Plays ``<sound_dir>/<key>.wav`` through ``winsound`` (Windows only).

    ``SND_ASYNC`` keeps the UI thread free; a missing file or a missing
    ``winsound`` module is skipped silently — sound effects are decoration and
    must never take the pet down.
    """

    def __init__(self, sound_dir: Path) -> None:
        self.sound_dir = Path(sound_dir)

    def path_for(self, key: str) -> Path:
        return self.sound_dir / f"{key}.wav"

    def play(self, key: str) -> None:
        import winsound  # imported lazily so non-Windows never pays for it

        path = self.path_for(key)
        if not path.is_file():
            return
        winsound.PlaySound(str(path), winsound.SND_ASYNC | winsound.SND_NODEFAULT)


def make_sound_player(sound_dir: Path) -> SilentPlayer | WinsoundPlayer:
    """Pick the best available player: winsound on Windows, silent elsewhere."""
    try:
        import winsound  # noqa: F401
    except ImportError:
        return SilentPlayer()
    return WinsoundPlayer(sound_dir)
