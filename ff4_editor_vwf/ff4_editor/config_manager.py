"""
ff4_editor/config_manager.py
Centralized configuration management for the editor.

Layers (later wins), each one a dict holding ONLY the keys explicitly set in it:

    EditorSettings defaults  <  global  <  file (files[<json basename>])  <  section override

The effective EditorConfig is always recomputed from the layers, so nothing that is
only effective (e.g. a section override) can leak into what gets saved.
"""

import os, json, shutil, logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from .config import EditorConfig
from .typed_config import (
    EditorSettings, SectionOverride, ConfigKey,
    validate_config_dict,
)

log = logging.getLogger("ff4_editor")

# Keys a per-section override may NOT change (global-only)
PROTECTED_KEYS = {ConfigKey.SHOW_BANDS.value}
_FONT_KEYS = (ConfigKey.CARD_FONT.value, ConfigKey.FONT_SIZE.value)
_VWF_KEYS = (ConfigKey.VWF_FONT_PNG.value, ConfigKey.VWF_GAP.value,
             ConfigKey.VWF_SPACE.value, ConfigKey.VWF_LINE_PITCH.value)


@dataclass
class ConfigManager:
    """Manages all editor configuration: global, per-file, per-section."""
    editor_config: EditorConfig
    config_path: str

    # Layers (explicit keys only)
    _global: dict = field(default_factory=dict)
    _file: dict = field(default_factory=dict)
    _section_overrides: dict = field(default_factory=dict)   # section -> SectionOverride
    _file_key: Optional[str] = None                          # basename of the open JSON

    # ── Effective settings ─────────────────────────────────────────────────────

    def _effective(self, section: Optional[str]) -> dict:
        eff = asdict(EditorSettings())
        eff.update(self._global)
        eff.update(self._file)
        ov = self._section_overrides.get(section) if section else None
        if ov:
            eff.update({k: v for k, v in ov.to_dict().items() if k not in PROTECTED_KEYS})
        return eff

    def apply_section_override(self, section: Optional[str]) -> None:
        """Recompute the effective config (defaults + global + file + section) and apply it."""
        for k, v in self._effective(section).items():
            if hasattr(self.editor_config, k):
                setattr(self.editor_config, k, v)
        self.editor_config.apply_font()

    # ── Dialog entry points ────────────────────────────────────────────────────

    def update_from_dialog(self, changed: dict, section: Optional[str],
                           section_only: bool) -> tuple[bool, bool]:
        """
        Apply changed settings from ViewDialog.
        section_only=True  -> stored as an override of `section` only.
        section_only=False -> stored in the global layer (and dropped from the file layer,
                              which would otherwise shadow it).
        Returns (font_changed, vwf_changed), computed from the effective values.
        """
        changed = validate_config_dict(changed)
        before = self._effective(section)

        if section_only and section:
            if changed:
                override = self._section_overrides.get(section, SectionOverride({}))
                for key, value in changed.items():
                    override.set(ConfigKey(key), value)
                self._section_overrides[section] = override
        else:
            self._global.update(changed)
            for key in changed:
                self._file.pop(key, None)

        self.apply_section_override(section)
        after = self._effective(section)
        font_changed = any(before[k] != after[k] for k in _FONT_KEYS)
        vwf_changed = any(before[k] != after[k] for k in _VWF_KEYS)
        return font_changed, vwf_changed

    def clear_section_override(self, section: str) -> None:
        """Remove per-section settings, revert to global."""
        self._section_overrides.pop(section, None)
        self.apply_section_override(section)

    # ── Persistence ────────────────────────────────────────────────────────────

    def load(self, filepath: Optional[str] = None) -> None:
        """Load config from disk. If filepath is given, also load that file's layer."""
        self._global, self._file, self._section_overrides = {}, {}, {}
        self._file_key = os.path.basename(filepath) if filepath else None
        cfg = self._read()
        self._global = validate_config_dict(cfg.get('global', {}))
        if self._file_key:
            raw = cfg.get('files', {}).get(self._file_key, {})
            if isinstance(raw, dict):
                self._file = validate_config_dict(raw)
                for section, ov in (raw.get('section_overrides') or {}).items():
                    if isinstance(ov, dict):
                        self._section_overrides[section] = SectionOverride.from_dict(ov)
        self.apply_section_override(None)

    def save(self, filepath: Optional[str] = None) -> None:
        """Save the layers to disk. The file layer and section overrides go under
        files[<basename>] when a file is open; the global layer under 'global'."""
        try:
            cfg = self._read()
            cfg['global'] = dict(self._global)
            cfg.setdefault('files', {})
            if filepath:
                entry = dict(self._file)
                entry['section_overrides'] = {
                    s: o.to_dict() for s, o in self._section_overrides.items()}
                cfg['files'][os.path.basename(filepath)] = entry
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            tmp = self.config_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
            os.replace(tmp, self.config_path)
        except Exception as e:
            log.warning(f"Failed to save config to {self.config_path}: {e}")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _read(self) -> dict:
        try:
            with open(self.config_path, encoding='utf-8-sig') as f:
                cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            log.warning(f"Failed to load config from {self.config_path}: {e}")
            return {}


def default_config_path() -> str:
    """~/.config/ff4_editor/config.json (or $FF4_EDITOR_CONFIG); on first run, migrates
    the legacy ff4_editor/ff4_editor_config.json that used to live inside the package."""
    env = os.environ.get("FF4_EDITOR_CONFIG")
    if env:
        return env
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation)
    path = os.path.join(base, "ff4_editor", "config.json")
    legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ff4_editor_config.json")
    if not os.path.exists(path) and os.path.isfile(legacy):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copy2(legacy, path)
        except OSError as e:
            log.warning(f"Could not migrate legacy config: {e}")
    return path


def create_config_manager(editor_config: EditorConfig) -> ConfigManager:
    """Factory function to create ConfigManager with the default path."""
    return ConfigManager(editor_config, default_config_path())
