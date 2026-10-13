"""Root-level compatibility import for the MaiBot adapter."""

from pathlib import Path
import sys


_BUNDLED_SOURCE = Path(__file__).resolve().parent / "src"
if _BUNDLED_SOURCE.is_dir() and str(_BUNDLED_SOURCE) not in sys.path:
    sys.path.insert(0, str(_BUNDLED_SOURCE))

try:
    from .maibot_plugin.adapter import DEFAULT_PREFIXES, DICE_COMMAND_PATTERN, DiceCommandAdapter, DiceDispatch
except ImportError:
    from maibot_plugin.adapter import DEFAULT_PREFIXES, DICE_COMMAND_PATTERN, DiceCommandAdapter, DiceDispatch

__all__ = ["DEFAULT_PREFIXES", "DICE_COMMAND_PATTERN", "DiceCommandAdapter", "DiceDispatch"]
