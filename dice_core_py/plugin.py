"""MaiBot plugin root entry point.

MaiBot loads this file as a package-like module whose package name is
generated from the manifest ID. Therefore implementation modules must be
imported relatively instead of assuming the plugin directory is on
``sys.path``.
"""

from pathlib import Path
import sys


_PLUGIN_ROOT = Path(__file__).resolve().parent
_BUNDLED_SOURCE = _PLUGIN_ROOT / "src"
if _BUNDLED_SOURCE.is_dir() and str(_BUNDLED_SOURCE) not in sys.path:
    sys.path.insert(0, str(_BUNDLED_SOURCE))

try:
    from .maibot_plugin.plugin import DicePlugin, DicePluginConfig
except ImportError:
    from maibot_plugin.plugin import DicePlugin, DicePluginConfig


def create_plugin() -> DicePlugin:
    return DicePlugin()


__all__ = ["DicePlugin", "DicePluginConfig", "create_plugin"]
