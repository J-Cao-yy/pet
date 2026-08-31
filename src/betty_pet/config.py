from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
    messages: tuple[str, ...] = (
        "不要随便打扰贝蒂哦。", "有事就说，贝蒂很忙的。", "喵？", "你这家伙。", "贝蒂才不孤单呢。",
    )

    def clamp_scale(self, value: float) -> float:
        return max(self.min_scale, min(self.max_scale, round(value, 2)))


def default_config(asset_dir: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    if asset_dir is not None:
        config.asset_dir = Path(asset_dir).expanduser().resolve()
    return config

