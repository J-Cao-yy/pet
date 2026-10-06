from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


DEFAULT_MANIFEST: dict[str, list[str]] = {
    "idle": ["stand.png", "stand-1.png", "stand-2.png", "stand-3.png"],
    "click": ["click.png"], "wave": ["hello.png"], "sleep": ["sleep.png"],
    "happy": ["happy.png"], "sit": ["sit.png"], "climb": ["climb.png", "climb-1.png"],
    "walk_left": ["walk-left.png", "walk-left-1.png", "walk-left-2.png", "walk-left-3.png", "walk-left-4.png"],
    "walk_right": ["walk-right.png", "walk-right-1.png", "walk-right-2.png"],
    "dragged": ["dragged.png"],
    "fall": ["fall.png"], "thrown": ["thrown.png"],
    "climb_wall_left": ["climb_wall_left.png"], "climb_wall_right": ["climb_wall_right.png"],
    "walk_ceiling": ["walk_ceiling.png"],
    "wipe_mouth": ["wipe mouth.png"],
}


ACTION_FALLBACKS: dict[str, tuple[str, ...]] = {
    "fall": ("fall", "idle"),
    "thrown": ("thrown", "click", "idle"),
    "dragged": ("dragged", "climb", "idle"),
    "chase_mouse": ("chase_mouse", "walk_left", "idle"),
    # Climbing (see docs/CLIMBING_DESIGN.md). There is no climb-wall or
    # ceiling-walk art yet, and the design deliberately ships the behaviour
    # first: these chains keep the pet animated with an existing frame instead
    # of freezing. Drop the real PNGs in and register them in the manifest and
    # the fallbacks simply stop being used.
    "climb_wall_left": ("climb_wall_left", "climb", "walk_left", "idle"),
    "climb_wall_right": ("climb_wall_right", "climb", "walk_right", "idle"),
    "walk_ceiling": ("walk_ceiling", "walk_left", "idle"),
}


class AssetCatalog:
    """Loads animation frames from a manifest without coupling assets to the UI."""

    def __init__(self, asset_dir: Path, manifest_path: Path | None = None) -> None:
        self.asset_dir = Path(asset_dir)
        self.manifest_path = manifest_path or self.asset_dir / "manifest.json"
        self.manifest = self._read_manifest()

    def _read_manifest(self) -> dict[str, list[str]]:
        if not self.manifest_path.is_file():
            return DEFAULT_MANIFEST.copy()
        with self.manifest_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("manifest must contain an object")
        return {str(key): [str(item) for item in value] for key, value in data.items()}

    def actions(self) -> tuple[str, ...]:
        return tuple(self.manifest)

    def resolve(self, action: str) -> str:
        """Map a semantic action onto the closest animation that actually exists.

        Physics and interaction verbs (``fall`` / ``thrown`` / ``dragged`` /
        ``chase_mouse``) have no art yet. Resolving through
        :data:`ACTION_FALLBACKS` keeps the pet animated with a stand-in frame
        until the matching PNGs land in the manifest, instead of freezing on
        the last one.
        """
        for candidate in ACTION_FALLBACKS.get(action, (action,)):
            if candidate in self.manifest:
                return candidate
        if "idle" in self.manifest:
            return "idle"
        return next(iter(self.manifest), action)

    def paths_for(self, action: str) -> list[Path]:
        names = self.manifest.get(action) or self.manifest.get("idle", [])
        existing = [self.asset_dir / name for name in names if (self.asset_dir / name).is_file()]
        if not existing:
            raise FileNotFoundError(f"No frames found for action '{action}' in {self.asset_dir}")
        return existing

    def load_frames(self, action: str, size: tuple[int, int]) -> list[Image.Image]:
        frames: list[Image.Image] = []
        for path in self.paths_for(action):
            with Image.open(path) as image:
                resized = image.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
                frames.append(self._remove_color_key_halo(resized))
        return frames

    @staticmethod
    def _remove_color_key_halo(image: Image.Image) -> Image.Image:
        """Make alpha edges binary so Windows' magenta color key cannot bleed through."""
        alpha = image.getchannel("A").point(lambda value: 255 if value >= 160 else 0)
        image.putalpha(alpha)
        return image

    def missing_files(self) -> list[Path]:
        return [self.asset_dir / name for names in self.manifest.values() for name in names if not (self.asset_dir / name).is_file()]
