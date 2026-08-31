"""Betty Pet: a customizable desktop pet built with Python and Tkinter."""

__version__ = "0.1.0"
from .behavior import (
    BehaviorAction,
    BehaviorRule,
    DialogueContext,
    LanguageProvider,
    TemplateLanguageProvider,
    ThresholdBehaviorEngine,
    default_behavior_rules,
)
from .state import PetState, PetStats, RecoveryMethod, RecoveryResult, StatRecovery

__all__ = [
    "BehaviorAction",
    "BehaviorRule",
    "DialogueContext",
    "LanguageProvider",
    "TemplateLanguageProvider",
    "ThresholdBehaviorEngine",
    "default_behavior_rules",
    "PetState",
    "PetStats",
    "RecoveryMethod",
    "RecoveryResult",
    "StatRecovery",
]
