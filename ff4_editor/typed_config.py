"""
ff4_editor/typed_config.py
Type-safe configuration system using dataclasses and enums.
Replaces stringly-typed keys with compile-time validation.
"""

from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any

from .errors import logger


class ConfigKey(Enum):
    """All valid configuration keys with their types."""

    # Layout
    CARD_ROWS = "card_rows"
    CARD_W = "card_w"
    SHOW_RULER = "show_ruler"
    RULER_CHARS = "ruler_chars"

    # Text limits
    WARN_CHARS = "warn_chars"
    OVER_CHARS = "over_chars"
    CHAR_LIMIT = "char_limit"
    LINE_LIMIT = "line_limit"
    AUTO_WRAP = "auto_wrap"

    # Font
    CARD_FONT = "card_font"
    FONT_SIZE = "font_size"

    # Visual
    SHOW_BANDS = "show_bands"

    # VWF
    VWF_ENABLED = "vwf_enabled"
    VWF_SCALE = "vwf_scale"
    VWF_LIMIT_PX = "vwf_limit_px"
    VWF_GAP = "vwf_gap"
    VWF_SPACE = "vwf_space"
    VWF_LINE_PITCH = "vwf_line_pitch"
    VWF_FONT_PNG = "vwf_font_png"

    @property
    def python_type(self) -> type | tuple[type, ...]:
        """Get the Python type for this config key."""
        return _KEY_TYPES[self]


@dataclass
class EditorSettings:
    """
    Type-safe persisted editor settings.
    All fields are serializable to JSON.
    """

    # Layout
    card_rows: int = 8
    card_w: int = 300
    show_ruler: bool = True
    ruler_chars: int = 28

    # Text limits
    warn_chars: int = 24
    over_chars: int = 26
    char_limit: int = 28
    line_limit: int = 0
    auto_wrap: bool = True

    # Font
    card_font: str = "Hack"
    font_size: int = 11

    # Visual
    show_bands: bool = True

    # VWF
    vwf_enabled: bool = True
    vwf_scale: int = 2
    vwf_limit_px: int = 224
    vwf_gap: int = 1
    vwf_space: int = 4
    vwf_line_pitch: int = 16
    vwf_font_png: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EditorSettings":
        """Create from dict (JSON), ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# Type of every setting, taken from the dataclass so there is a single list of fields.
_KEY_TYPES: dict[ConfigKey, Any] = {ConfigKey(f.name): f.type for f in fields(EditorSettings)}


class SectionOverride:
    """Type-safe section-specific settings."""

    def __init__(self, settings: dict[str, Any]):
        self._settings = settings

    def get(self, key: ConfigKey, default: Any = None) -> Any:
        return self._settings.get(key.value, default)

    def set(self, key: ConfigKey, value: Any) -> None:
        if not isinstance(value, key.python_type):
            raise TypeError(f"{key.value} must be {key.python_type}, got {type(value)}")
        self._settings[key.value] = value

    def to_dict(self) -> dict:
        return dict(self._settings)

    @classmethod
    def from_dict(cls, d: dict) -> "SectionOverride":
        return cls(validate_config_dict(d))  # validated copy, not the caller's dict


# Allowed inclusive ranges for numeric keys (anything outside is dropped with a warning).
_RANGES: dict[ConfigKey, tuple[int, int]] = {
    ConfigKey.CARD_ROWS: (1, 50),
    ConfigKey.CARD_W: (100, 4000),
    ConfigKey.RULER_CHARS: (1, 200),
    ConfigKey.WARN_CHARS: (1, 500),
    ConfigKey.OVER_CHARS: (1, 500),
    ConfigKey.CHAR_LIMIT: (1, 500),
    ConfigKey.LINE_LIMIT: (0, 100),
    ConfigKey.FONT_SIZE: (4, 96),
    ConfigKey.VWF_SCALE: (1, 8),
    ConfigKey.VWF_LIMIT_PX: (8, 1024),
    ConfigKey.VWF_GAP: (0, 8),
    ConfigKey.VWF_SPACE: (1, 16),
    ConfigKey.VWF_LINE_PITCH: (8, 64),
}


def _coerce(key: ConfigKey, value: Any) -> Any:
    """Return the value converted to the key's type, or raise ValueError."""
    t = key.python_type
    if t is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "1", "yes", "on"):
            return True
        if isinstance(value, str) and value.lower() in ("false", "0", "no", "off"):
            return False
        raise ValueError("not a bool")
    if t is int:
        if isinstance(value, bool):
            raise ValueError("bool is not an int")
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError) as e:
            raise ValueError("not an int") from e
    if t is str:
        return value if isinstance(value, str) else str(value)
    raise ValueError("unsupported type")


def validate_config_dict(d: dict) -> dict:
    """
    Validate and coerce a config dict, returning only valid typed keys.
    Unknown keys, wrong types, out-of-range numbers and invalid colours are dropped
    (and logged), never raised.
    """
    result = {}
    if not isinstance(d, dict):
        return result
    for key in ConfigKey:
        if key.value not in d:
            continue
        try:
            value = _coerce(key, d[key.value])
            if key in _RANGES:
                lo, hi = _RANGES[key]
                if not lo <= value <= hi:
                    raise ValueError(f"out of range {lo}..{hi}")
        except ValueError as e:
            logger.warning(f"config: dropped {key.value}={d[key.value]!r} ({e})")
            continue
        result[key.value] = value
    return result
