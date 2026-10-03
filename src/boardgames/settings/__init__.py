"""参数系统：描述、校验、持久化。"""

from boardgames.settings.schema import (
    AI_TYPES,
    GROUPS,
    MODE_LABELS,
    MODES,
    PLAYER_TYPE_LABELS,
    PLAYER_TYPES,
    SPEC_BY_KEY,
    SPECS,
    ParamSpec,
)
from boardgames.settings.store import SCHEMA_VERSION, Settings, default_settings_path

__all__ = [
    "AI_TYPES",
    "GROUPS",
    "MODE_LABELS",
    "MODES",
    "PLAYER_TYPE_LABELS",
    "PLAYER_TYPES",
    "SCHEMA_VERSION",
    "SPECS",
    "SPEC_BY_KEY",
    "ParamSpec",
    "Settings",
    "default_settings_path",
]
