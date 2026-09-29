from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .physics import PhysicsConfig
from .store import DEFAULT_DB_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class AppConfig:
    """Runtime settings kept in one place for a future settings UI."""

    asset_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "assets")
    base_size: int = 128
    scale: float = 1.0
    min_scale: float = 0.3
    max_scale: float = 2.5
    random_actions: bool = True
    idle_delay_ms: tuple[int, int] = (6_000, 15_000)
    action_duration_ms: int = 1_200
    dialog_duration_ms: int = 1_500
    frame_interval_ms: int = 180
    messages: tuple[str, ...] = (
        "不要随便打扰贝蒂哦。", "有事就说，贝蒂很忙的。", "喵？", "你这家伙。", "贝蒂才不孤单呢。",
    )
    persist: bool = True
    db_path: Path = field(default_factory=lambda: DEFAULT_DB_PATH)
    autosave_interval_ms: int = 60_000
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    physics_interval_ms: int = 16
    floor_offset_px: int = 48
    chase_speed_px: float = 110.0
    chase_deadzone_px: float = 24.0
    hover_delay_ms: int = 800
    initial_margin_px: int = 40
    perch_poll_ms: int = 500
    tray_poll_ms: int = 250
    # ``None`` means "no opinion": the stored setting wins. ``--sound`` /
    # ``--no-sound`` set it explicitly and override the save file for one run.
    sound_enabled: bool | None = None
    focus_minutes: int = 25
    focus_break_minutes: int = 5
    focus_poll_ms: int = 1_000
    focus_affection: float = 3.0
    # Climbing (see docs/CLIMBING_DESIGN.md). ``wall_reach_px`` is how far inside
    # the screen edge the pet starts gripping: 0 means it will only climb when
    # its own corner is exactly on the edge, which the physics never quite
    # produces, so the tolerance is explicit.
    climb_speed_px: float = 140.0
    climb_distance_px: tuple[int, int] = (90, 320)
    wall_reach_px: float = 3.0
    # The screen edge is not a line but a climbable *band* (see
    # ``docs/CLIMBING_DESIGN.md`` §7): inside it gravity is suspended and the
    # pet may shuffle inwards/outwards; push past the inner edge and it peels
    # off and falls. ``climb_lean_chance`` is the odds that, at the end of a
    # vertical stretch, the pet starts drifting inwards instead of just picking
    # another up/down run.
    climb_band_px: int = 60
    climb_lean_chance: float = 0.15
    # Odds, at the end of each climb stretch, that the pet hands the grip back
    # to gravity and falls from where it is. Kept low on purpose: with a band
    # the pet has somewhere to roam, so leaving the wall should be the
    # exception rather than the usual end of a stretch (0.15 + 0.15 = 30%).
    climb_release_chance: float = 0.15

    def clamp_scale(self, value: float) -> float:
        return max(self.min_scale, min(self.max_scale, round(value, 2)))


def default_config(
    asset_dir: str | Path | None = None,
    *,
    db_path: str | Path | None = None,
    persist: bool = True,
) -> AppConfig:
    config = AppConfig(persist=persist)
    if asset_dir is not None:
        config.asset_dir = Path(asset_dir).expanduser().resolve()
    if db_path is not None:
        config.db_path = Path(db_path).expanduser()
    return config

