from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from .physics import PhysicsConfig
from .store import DEFAULT_DB_PATH


# Frozen (PyInstaller): read-only resources live in the extraction dir that
# ``--add-data`` populated; source runs resolve the repo root two levels up.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
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
    # 自主行为的"精致化"参数（见 window.py 的 _random_action / _neglect_nap）：
    # 随机选到与上次相同的动作时最多重摇几次，避免"连环睡觉"这种复读感；
    # 无人互动超过 neglect_minutes 就自己打个小盹抱怨一句；
    # nap_hour_start..end（可跨午夜）是深夜犯困时段，该时段随机行为有
    # nap_hour_chance 的概率直接变成打盹。
    action_rerolls: int = 2
    neglect_minutes: float = 5.0
    nap_hour_start: int = 23
    nap_hour_end: int = 7
    nap_hour_chance: float = 0.4
    action_duration_ms: int = 1_200
    dialog_duration_ms: int = 1_500
    # 240ms/帧比 180ms 慢 25%，动作更从容；帧驱动是固定间隔的 Tk after 定时器，
    # 这个量级不会产生卡顿感。行走步进速度（movement.MovementPlanner）随之从
    # 150px/s 降到 125px/s，避免"帧慢了、脚在滑"的分离感。
    frame_interval_ms: int = 240
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
    # A "专注" is now several focus/break rounds back to back. ``rounds = 1``
    # is the original single-cycle behaviour; every ``long_break_every``-th
    # break of a run is a long one (0 disables that).
    focus_rounds: int = 2
    focus_long_break_minutes: int = 15
    focus_long_break_every: int = 2
    # Light interactions (see betty_pet.petting). A poke or a stroke earns a
    # little affection - the everyday-contact source the roadmap called out.
    # Both kinds share one daily cap, and a cooldown keeps clicking the pet
    # from being an idle-clicker's dream.
    pet_affection_click: float = 1.0
    pet_affection_stroke: float = 2.0
    pet_affection_daily_limit: int = 10
    pet_affection_cooldown_ms: int = 60_000
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

