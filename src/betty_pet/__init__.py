"""Betty Pet: a customizable desktop pet built with Python and Tkinter."""

__version__ = "0.5.0"
from .audio import SOUND_KEYS, SilentPlayer, SoundPlayer
from .behavior import (
    BehaviorAction,
    BehaviorRule,
    DialogueContext,
    LanguageProvider,
    TemplateLanguageProvider,
    ThresholdBehaviorEngine,
    default_behavior_rules,
)
from .desktop import (
    NullWindowProbe,
    WindowProbe,
    WindowRect,
    Win32WindowProbe,
    make_probe,
    perch_bounds,
)
from .items import Item, ItemOutcome, apply_item, default_items, items_by_group
from .movement import Direction, MovementPlan, MovementPlanner, chase_direction, horizontal_target
from .physics import (
    Bounds,
    DragTracker,
    MotionEvents,
    MotionState,
    PhysicsConfig,
    bounds_for,
    clamp_speed,
    clamp_to_bounds,
)
from .scheduler import Clock, Job, ManualClock, Scheduler, TkClock
from .state import (
    AFFECTION_PER_LEVEL,
    AFFECTION_TITLES,
    PetState,
    PetStats,
    affection_level,
    affection_title,
    affection_to_next_level,
)
from .store import MemoryStateStore, SQLiteStateStore, StateStore
from .tray import NullTray, TrayAction, TrayIcon, make_tray

__all__ = [
    "SOUND_KEYS",
    "SilentPlayer",
    "SoundPlayer",
    "BehaviorAction",
    "BehaviorRule",
    "DialogueContext",
    "LanguageProvider",
    "TemplateLanguageProvider",
    "ThresholdBehaviorEngine",
    "default_behavior_rules",
    "NullWindowProbe",
    "WindowProbe",
    "WindowRect",
    "Win32WindowProbe",
    "make_probe",
    "perch_bounds",
    "Item",
    "ItemOutcome",
    "apply_item",
    "default_items",
    "items_by_group",
    "Direction",
    "MovementPlan",
    "MovementPlanner",
    "chase_direction",
    "horizontal_target",
    "Bounds",
    "DragTracker",
    "MotionEvents",
    "MotionState",
    "PhysicsConfig",
    "bounds_for",
    "clamp_speed",
    "clamp_to_bounds",
    "Clock",
    "Job",
    "ManualClock",
    "Scheduler",
    "TkClock",
    "AFFECTION_PER_LEVEL",
    "AFFECTION_TITLES",
    "PetState",
    "PetStats",
    "affection_level",
    "affection_title",
    "affection_to_next_level",
    "MemoryStateStore",
    "SQLiteStateStore",
    "StateStore",
    "NullTray",
    "TrayAction",
    "TrayIcon",
    "make_tray",
]
