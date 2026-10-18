"""
ff4_editor/model/json_model.py

Loads, owns and mutates ff4-en-data.json.
Section capacities are read from the companion ff4-*.lnk linker script
(same directory as the JSON) via the linker module.
Falls back to the JSON's assembly[key].range field if the LNK is not found.
"""

import os
import re
from collections.abc import Iterator
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..constants import (
    DICT_KEY,
    ENCODER_SPLITS,
    FIXED_FIELD_OVERRIDES_ES,
    POINTER_OVERHEAD_UNVERIFIED,
    SEGMENT_EXTRA_BYTES,
    TEXT_SECTIONS,
)
from ..errors import FileSaveError, logger, safe_json_load, safe_json_save
from ..i18n import tr
from ..util.text_processing import set_char_names
from .linker import (
    Capacity,
    _lnk_path_for_json,
    capacities_from_map,
    map_path_for_json,
    parse_lnk_capacities,
)
from .textcodec import DEFAULT_ENCODINGS, TextCodec, shared_bytes


class FF4Model(QObject):
    """
    Owns the parsed JSON data. All writes go through this class so that
    dirty-tracking and signal emission are centralised.

    Signals
    -------
    section_changed(key)   - emitted after any entry in `key` is mutated
    entry_changed(key, i)  - same, but says which entry (int, or (i, j) for mapDialog)
    loaded()               - emitted after a successful file load
    """

    section_changed = Signal(str)
    entry_changed = Signal(str, object)  # (key, idx) of the entry that was written
    loaded = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._data: dict = {}
        self._filepath: str | None = None
        self._codecs: dict[str, TextCodec] = {}
        self._caps: dict = {}  # section -> byte capacity
        self._seg_caps: dict[str, tuple[int, int]] = {}  # split sections: capacity per segment
        self._caps_exact: dict[str, bool] = {}  # section -> capacity is exact, not an estimate
        self._caps_source: str = ""  # 'lnk' or 'json'
        self.dirty_keys: set[str] = set()
        self._fixed: dict[str, int] = {}  # fixedLength section -> max characters per entry
        self._used: dict[str, int] = {}  # section -> bytes in use (kept up to date incrementally)

    def get_entry(self, key: str, idx: int | tuple[int, int]) -> str:
        """Retrieve the existing string to store in the undo command."""
        items = self._data.get("obj", {}).get(key, [])
        dk = DICT_KEY.get(key)

        if isinstance(idx, tuple):
            i, j = idx
            if 0 <= i < len(items) and isinstance(items[i], list) and 0 <= j < len(items[i]):
                return items[i][j]
        elif 0 <= idx < len(items):
            if dk and isinstance(items[idx], dict):
                return items[idx].get(dk, "")
            else:
                return items[idx]
        return ""

    # -- File I/O --------------------------------------------------------------

    def load(self, path: str) -> None:
        """Load `path`. Raises FileLoadError; on failure the previous data is kept."""
        data = safe_json_load(path, tr("Datos JSON de FF4"))
        self._data = data
        self._filepath = path
        self._build_codecs()
        self.dirty_keys.clear()
        self._used.clear()
        self._compute_capacities()
        self._build_char_names()
        self.loaded.emit()

    def save(self) -> None:
        """Atomic save of the whole JSON. Raises FileSaveError (data stays dirty)."""
        if not self._filepath:
            raise FileSaveError("", tr("no hay ningún archivo abierto"))
        safe_json_save(self._filepath, self._data, "FF4 data JSON")
        self.dirty_keys.clear()

    # -- Properties ------------------------------------------------------------

    @property
    def filepath(self) -> str | None:
        return self._filepath

    @property
    def char_table_text(self) -> dict:
        """charTable.text.char ({'0x42': 'A', ...}) of the loaded JSON."""
        try:
            return self._data["charTable"]["text"]["char"]
        except (KeyError, TypeError) as e:
            logger.warning(f"Missing charTable.text.char in data: {e}")
            return {}

    def _build_codecs(self) -> None:
        tables = self._data.get("charTable", {})
        defs = self._data.get("textEncoding") or DEFAULT_ENCODINGS
        self._codecs = {name: TextCodec(d, tables) for name, d in defs.items()}

    @property
    def encoding_names(self) -> list[str]:
        return sorted(self._codecs)

    def codec_for(self, key: str | None) -> TextCodec:
        """The text codec the build uses for section `key` (its text field's `encoding`)."""
        name = _text_encoding(self._data.get("assembly", {}).get(key or "", {}).get("assembly"))
        codec = self._codecs.get(name or "") or self._codecs.get("dialog")
        return codec if codec is not None else TextCodec({}, {})

    @property
    def caps_source(self) -> str:
        """'lnk' if capacities came from the LNK file, 'json' if fallback."""
        return self._caps_source

    def capacity(self, key: str) -> int:
        """Byte capacity, or for fixedLength sections the characters allowed per entry."""
        return self._fixed.get(key) or self._caps.get(key, 0)

    def capacity_exact(self, key: str) -> bool:
        """False when capacity() is only an estimate (so an 'overflow' may not be real)."""
        return key in self._fixed or self._caps_exact.get(key, False)

    def is_fixed(self, key: str) -> bool:
        """True for fixedLength sections: each entry has its own slot, so the meaningful
        figures are the longest entry vs the slot size, not a byte total."""
        return key in self._fixed

    def section_items(self, key: str) -> list:
        return self._data.get("obj", {}).get(key, [])

    def map_properties(self) -> list:
        return self._data.get("obj", {}).get("mapProperties", [])

    def map_titles(self) -> list:
        return self._data.get("obj", {}).get("mapTitle", [])

    # -- Writes ----------------------------------------------------------------

    def set_entry(self, key: str, idx: int | tuple[int, int], json_text: str) -> None:
        """
        Write json_text into data[key][idx].
        idx is an int for normal entries, or (i, j) for mapDialog sub-strings.
        """
        items = self._data.get("obj", {}).get(key, [])
        dk = DICT_KEY.get(key)

        if self.get_entry(key, idx) == json_text and self._valid_index(items, idx):
            return  # nothing to change: don't mark dirty
        if not self._valid_index(items, idx):
            logger.warning(f"set_entry: index {idx!r} out of range for '{key}' - ignored")
            return

        old_text = self.get_entry(key, idx)
        if isinstance(idx, tuple):
            i, j = idx
            items[i][j] = json_text
        elif dk and isinstance(items[idx], dict):
            items[idx][dk] = json_text
        else:
            items[idx] = json_text

        # Mark assembly dirty (consumed by the encoder / make rule)
        asm = self._data.get("assembly", {}).get(key)
        if asm:
            asm["isDirty"] = True

        if key in self._used:  # keep the cached byte count current without re-encoding everything
            if self._is_shared(key):
                del self._used[key]  # shared storage: an edit can change what is deduplicated
            else:
                self._used[key] += self._entry_cost(key, json_text) - self._entry_cost(key, old_text)
        self.dirty_keys.add(key)
        self.entry_changed.emit(key, idx)
        self.section_changed.emit(key)

        # If characterNames was edited, rebuild CHAR_NAMES and notify
        if key == "characterNames":
            self._build_char_names()

    # -- Search ----------------------------------------------------------------

    def iter_entries(self, keys: list[str] | None = None) -> Iterator[tuple[str, int | tuple[int, int], str]]:
        """Yield (key, idx, text) for every string entry (idx is an int, or (i, j) for mapDialog)."""
        for key in keys if keys is not None else TEXT_SECTIONS:
            dk = DICT_KEY.get(key)
            for i, item in enumerate(self.section_items(key)):
                if isinstance(item, list):
                    for j, s in enumerate(item):
                        if isinstance(s, str):
                            yield key, (i, j), s
                elif isinstance(item, dict):
                    if dk and isinstance(item.get(dk), str):
                        yield key, i, item[dk]
                elif isinstance(item, str):
                    yield key, i, item

    @staticmethod
    def make_matcher(query: str, case_sensitive: bool = False, regex: bool = False) -> re.Pattern:
        """Compiled pattern for `query`. Raises ValueError for an empty query or a bad regex."""
        if not query:
            raise ValueError(tr("la búsqueda está vacía"))
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return re.compile(query if regex else re.escape(query), flags)
        except re.error as e:
            raise ValueError(tr("expresión regular inválida: {error}").format(error=e)) from e

    def find_all(
        self, pattern: re.Pattern, keys: list[str] | None = None
    ) -> list[tuple[str, int | tuple[int, int], str]]:
        """All entries whose stored text matches `pattern` (searches the JSON text,
        so control codes such as \\wait or \\char03 are searchable)."""
        return [(k, i, t) for k, i, t in self.iter_entries(keys) if pattern.search(t)]

    # -- Byte budget -----------------------------------------------------------

    @staticmethod
    def _valid_index(items: list, idx: Any) -> bool:
        """True if idx addresses an existing entry (negative indexes are rejected)."""
        if isinstance(idx, tuple):
            i, j = idx
            return 0 <= i < len(items) and isinstance(items[i], list) and 0 <= j < len(items[i])
        return isinstance(idx, int) and 0 <= idx < len(items)

    def used_bytes(self, key: str) -> int:
        """Bytes the section occupies once encoded (cached; set_entry keeps it current)."""
        if key in self._fixed:  # fixedLength: the longest entry (compared with the slot size)
            return max((self._fixed_cost(key, i) for i in self.section_items(key)), default=0)
        if key not in self._used:
            self._used[key] = self._compute_used_bytes(key)
        return self._used[key]

    def _fixed_cost(self, key: str, item: Any) -> int:
        """Bytes one fixedLength entry takes (its codec has no terminator and no DTE)."""
        text = item.get(DICT_KEY.get(key, ""), "") if isinstance(item, dict) else item
        return self.codec_for(key).size(text) if isinstance(text, str) else 0

    def fixed_overflows(self, key: str) -> list[int]:
        """Indices of fixedLength entries longer than their slot."""
        limit = self._fixed.get(key, 0)
        return [i for i, it in enumerate(self.section_items(key)) if self._fixed_cost(key, it) > limit]

    def _entry_cost(self, key: str, text: str) -> int:
        """Bytes of one entry as the real encoder writes it (every string gets its terminator)."""
        return self.codec_for(key).size(text)

    def _is_shared(self, key: str) -> bool:
        """'Shared array' sections: the encoder stores equal item bytes once (no terminator,
        isSequential or itemLength in the definition) and strings are not lists."""
        a = self._data.get("assembly", {}).get(key, {})
        items = self.section_items(key)
        return (
            a.get("type") == "array"
            and a.get("terminator") is None
            and not a.get("isSequential")
            and not a.get("itemLength")
            and not any(isinstance(i, list) for i in items)
        )

    def _compute_used_bytes(self, key: str) -> int:
        items = self.section_items(key)
        dk = DICT_KEY.get(key)
        codec = self.codec_for(key)
        if self._is_shared(key):
            texts = [(i.get(dk, "") if isinstance(i, dict) else i) for i in items]
            encoded = [codec.encode(t if isinstance(t, str) else "") for t in texts]
            return sum(self._segment_used(key, encoded))
        total = 0
        for item in items:
            if isinstance(item, list):  # mapDialog: several strings per map, each terminated
                total += sum(codec.size(s) for s in item if isinstance(s, str))
            elif isinstance(item, dict):
                total += codec.size(item.get(dk, ""))
            elif isinstance(item, str):
                total += codec.size(item)
        return total

    def _segment_used(self, key: str, encoded: list[bytes] | None = None) -> list[int]:
        """Bytes per segment the encoder writes separately (one, or two for ENCODER_SPLITS)."""
        if encoded is None:
            dk = DICT_KEY.get(key)
            codec = self.codec_for(key)
            texts = [(i.get(dk, "") if isinstance(i, dict) else i) for i in self.section_items(key)]
            encoded = [codec.encode(t if isinstance(t, str) else "") for t in texts]
        split = ENCODER_SPLITS.get(key, (len(encoded), ""))[0]
        if split >= len(encoded):
            return [shared_bytes(encoded)]
        return [shared_bytes(encoded[:split]), shared_bytes(encoded[split:])]

    def overflow_bytes(self, key: str) -> int:
        """Bytes over capacity, 0 when it fits.  Split sections are checked per segment (each
        pool must fit its own segment), not only in total.  Only meaningful if capacity_exact."""
        cap, used = self.capacity(key), self.used_bytes(key)
        over = max(0, used - cap)
        seg = self._seg_caps.get(key)
        if seg and self._is_shared(key):
            for u, c in zip(self._segment_used(key), seg, strict=False):
                over = max(over, u - c)
        return over

    def entry_byte_cost(self, json_text: str, key: str | None = None) -> int:
        """Bytes one string takes in the ROM (characters for fixedLength sections)."""
        return self.codec_for(key).size(json_text)

    # -- Internal --------------------------------------------------------------

    def _compute_capacities(self) -> None:
        """
        Capacity per section, best source first:
          1. the ld65 map (rom/<name>.map) of the last build, if newer than the .lnk: exact;
          2. the .lnk script: exact only for segments whose neighbours have explicit `start =`;
          3. the JSON `range`: the ORIGINAL ROM layout, so only an estimate (stale for the
             Spanish build, whose banks are laid out differently).
        """
        self._caps = {}
        self._caps_exact = {}
        self._seg_caps = {}
        self._caps_source = "json"

        lnk_path = _lnk_path_for_json(self._filepath) if self._filepath else None
        lnk_caps: dict[str, Capacity] = {}
        if lnk_path:
            lnk_caps = parse_lnk_capacities(lnk_path)
            if lnk_caps:
                self._caps_source = "lnk"
                map_path = map_path_for_json(self._filepath or "")
                if map_path and _newer_or_equal(map_path, lnk_path):
                    mapped = capacities_from_map(lnk_path, map_path)
                    if mapped:
                        lnk_caps.update(mapped)
                        self._caps_source = "map"

        json_caps: dict[str, int] = {}
        for key in TEXT_SECTIONS:
            a = self._data.get("assembly", {}).get(key, {})
            r = a.get("range", "")
            if "-" in r:
                try:
                    s, e = [int(x, 16) for x in r.split("-")]
                    json_caps[key] = e - s + 1  # inclusive range
                except ValueError:
                    pass

        self._compute_fixed_limits()

        for key in TEXT_SECTIONS:
            if key in lnk_caps:
                # a segment also holds the pointer table (and a few fixed extras): text gets the rest
                self._caps[key] = lnk_caps[key].bytes - self._overhead(key, len(self.section_items(key)))
                self._caps_exact[key] = lnk_caps[key].exact
            elif key in json_caps:
                self._caps[key] = json_caps[key]
                self._caps_exact[key] = False

        # Sections the encoder splits in two segments (see ENCODER_SPLITS) get both capacities.
        for key, (first_bank, extra_key) in ENCODER_SPLITS.items():
            extra = lnk_caps.get(extra_key)
            if key in self._caps and extra and len(self.section_items(key)) > first_bank:
                n_rest = max(0, len(self.section_items(key)) - first_bank)
                extra_cap = extra.bytes - self._overhead(key, n_rest, extras=False)
                # _caps[key] is the first segment minus the pointers of ALL entries; the second
                # segment's pointers (n_rest) belong to it, not to the first
                first_cap = self._caps[key] + self._overhead(key, n_rest, extras=False)
                self._seg_caps[key] = (first_cap, extra_cap)
                self._caps[key] = first_cap + extra_cap
                self._caps_exact[key] = self._caps_exact[key] and extra.exact

    def _overhead(self, key: str, entries: int, extras: bool = True) -> int:
        """Bytes of a linker segment that are not text: the pointer table and fixed extras."""
        total = SEGMENT_EXTRA_BYTES.get(key, 0) if extras else 0
        a = self._data.get("assembly", {}).get(key, {})
        if a.get("pointerTable") and key not in POINTER_OVERHEAD_UNVERIFIED:
            total += 2 * entries
        return total

    def _compute_fixed_limits(self) -> None:
        """Slot size of every fixedLength section: itemLength - begin from the JSON, never below
        the longest entry already in the file (the game builds with it, so the JSON is stale),
        and the Spanish build's widened fields."""
        self._fixed = {}
        asm_all = self._data.get("assembly", {})
        es = os.path.basename(self._filepath or "").lower().startswith("ff4-es")
        for key in TEXT_SECTIONS:
            a = asm_all.get(key, {})
            sub = a.get("assembly", {})
            begin = 0
            if sub.get("encoding") != "fixedLength":
                fields = [f for f in sub.get("assembly", {}).values() if isinstance(f, dict)]
                field = next((f for f in fields if f.get("encoding") == "fixedLength"), None)
                if field is None:
                    continue
                begin = int(field.get("begin", 0))
            limit = int(a.get("itemLength", 0)) - begin
            if es:
                limit = max(limit, FIXED_FIELD_OVERRIDES_ES.get(key, 0))
            longest = max((self._fixed_cost(key, it) for it in self.section_items(key)), default=0)
            if limit > 0:
                self._fixed[key] = max(limit, longest)

    def _build_char_names(self) -> None:
        new_names: dict[int, str] = {}
        for i, name in enumerate(self._data.get("obj", {}).get("characterNames", [])):
            if isinstance(name, str) and name.strip():
                new_names[i] = name.strip()
        set_char_names(new_names)


def _text_encoding(definition: Any) -> str | None:
    """Name of the `encoding` of the first text field inside an assembly definition."""
    if not isinstance(definition, dict):
        return None
    if definition.get("type") == "text":
        enc = definition.get("encoding")
        return enc if isinstance(enc, str) else None
    for sub in definition.values():
        found = _text_encoding(sub)
        if found:
            return found
    return None


def _newer_or_equal(path: str, other: str) -> bool:
    """True if `path` exists and was modified no earlier than `other`."""
    try:
        return os.path.getmtime(path) >= os.path.getmtime(other)
    except OSError:
        return False
