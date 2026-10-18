"""
ff4_editor/ui_sections.py
sidebar list and section -> card list loading.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QListWidgetItem,
    QStyle,
)

from .constants import DIALOG_SECTIONS, DICT_KEY, TEXT_SECTIONS
from .i18n import tr
from .widgets import CardData


class SectionsMixin:
    """Mixin of FF4Editor: sidebar list and section -> card list loading."""

    # ── Sidebar ───────────────────────────────────────────────────────────────

    KEY_ROLE = Qt.ItemDataRole.UserRole

    def _item_key(self, item) -> str | None:
        return item.data(self.KEY_ROLE) if item is not None else None

    def _populate_sidebar(self):
        self.section_list.blockSignals(True)
        self.section_list.clear()
        for key in TEXT_SECTIONS:
            if not self._model.section_items(key):
                continue
            item = QListWidgetItem()
            item.setData(self.KEY_ROLE, key)
            self.section_list.addItem(item)
            self._refresh_sidebar_item(key, item)
        self.section_list.blockSignals(False)
        self._cur_section = None

    def _refresh_sidebar_item(self, key: str, item=None):
        if item is None:
            for i in range(self.section_list.count()):
                it = self.section_list.item(i)
                if self._item_key(it) == key:
                    item = it
                    break
        if item is None:
            return
        cap = self._model.capacity(key)
        used = self._model.used_bytes(key)
        S = QStyle.StandardPixmap
        item.setText(tr(TEXT_SECTIONS.get(key, key)))
        font = item.font()
        font.setBold(key in self._model.dirty_keys)
        item.setFont(font)
        fixed = self._model.is_fixed(key)
        if fixed:
            bad = self._model.fixed_overflows(key)
            if bad:
                item.setIcon(self.style().standardIcon(S.SP_MessageBoxCritical))
                tip = tr("{n} entradas exceden los {cap} caracteres (primera: #{first})").format(
                    n=len(bad), cap=cap, first=bad[0]
                )
            else:
                item.setIcon(QIcon())
                tip = tr("Entrada más larga: {used} de {cap} caracteres").format(used=used, cap=cap)
        elif cap and not self._model.capacity_exact(key):
            # an estimate (JSON range / linker script) must not claim an overflow
            item.setIcon(QIcon())
            tip = tr(
                "{used} B usados · capacidad estimada ≈ {cap} B (compilá para medirla con exactitud)"
            ).format(used=used, cap=cap)
        elif cap and self._model.overflow_bytes(key):
            item.setIcon(self.style().standardIcon(S.SP_MessageBoxCritical))
            tip = tr("Excede la capacidad por {n} bytes ({used} B de {cap} B)").format(
                n=self._model.overflow_bytes(key), used=used, cap=cap
            )
        elif cap and used / cap > 0.90:
            item.setIcon(self.style().standardIcon(S.SP_MessageBoxWarning))
            tip = tr("Casi llena: {used} B de {cap} B ({pct} %)").format(
                used=used, cap=cap, pct=used * 100 // cap
            )
        else:
            item.setIcon(QIcon())
            tip = (
                tr("{used} B de {cap} B").format(used=used, cap=cap)
                if cap
                else tr("Sin información de capacidad en la ROM")
            )
        if key in self._model.dirty_keys:
            tip += tr(" · modificada sin guardar")
        item.setToolTip(tip)

    def _on_section_selected(self, current, _previous=None):
        key = self._item_key(current)
        if key is None:
            return
        self._cur_section = key
        self.config_mgr.apply_section_override(key)
        self._load_section(key)

    # ── Section loading → CardData list ──────────────────────────────────────

    def _load_section(self, key: str):
        items = self._model.section_items(key)
        filt = self.filter_edit.text().lower()
        is_dlg = key in DIALOG_SECTIONS
        dk = DICT_KEY.get(key)

        labels = self._update_map_selector(key, items)
        cards: list[CardData] = []
        for i, item in enumerate(items):
            if isinstance(item, list):  # mapDialog: sub-strings per map
                cards += self._map_entry_cards(key, i, item, labels.get(i, ""), filt)
                continue
            text = (
                item.get(dk, "")
                if (dk and isinstance(item, dict))
                else (item if isinstance(item, str) else str(item))
            )
            if self._matches(filt, text, i):
                cards.append(
                    CardData(key, i, f"#{i:03d}", is_dlg, text, self._model.entry_byte_cost(text, key))
                )

        self._canvas.load_cards(cards)
        self._refresh_budget(key)
        if filt:
            self.count_lbl.setText(
                tr("{n} entradas  ·  {shown} mostradas").format(n=len(items), shown=len(cards))
            )
        else:
            self.count_lbl.setText(tr("{n} entradas").format(n=len(items)))
        if self.verbose:
            print(f"[section] {TEXT_SECTIONS.get(key, key)}: {len(items)} entries, {len(cards)} cards")

    @staticmethod
    def _matches(filt: str, text: str, index: int, label: str = "") -> bool:
        """Filter test: empty filter matches; otherwise text, entry number or map name."""
        return not filt or filt in text.lower() or filt in str(index) or filt in label.lower()

    def _update_map_selector(self, key: str, items: list) -> dict[int, str]:
        """Show/fill the map combo for mapDialog; returns {map index: title}."""
        if key != "mapDialog":
            self._map_row.setVisible(False)
            self._cur_map_idx = 0
            return {}
        mp = self._model.map_properties()
        mt = self._model.map_titles()
        labels: dict[int, str] = {}
        for li in range(len(items)):
            tidx = mp[li].get("title", 0) if li < len(mp) and isinstance(mp[li], dict) else 0
            labels[li] = mt[tidx] if tidx < len(mt) else ""
        self._map_combo.blockSignals(True)
        self._map_combo.clear()
        for li, name in labels.items():
            self._map_combo.addItem(f"#{li:03d}  {name}")
        self._cur_map_idx = max(0, min(self._cur_map_idx, len(items) - 1))
        self._map_combo.setCurrentIndex(self._cur_map_idx)
        self._map_combo.blockSignals(False)
        self._map_row.setVisible(True)
        return labels

    def _map_entry_cards(self, key: str, i: int, item: list, label: str, filt: str) -> list:
        """Cards of one map. With a filter: every matching map; without: only the selected one."""
        all_text = " ".join(s for s in item if isinstance(s, str))
        if key == "mapDialog" and not filt:
            if i != self._cur_map_idx:
                return []
        elif not self._matches(filt, all_text, i, label if key == "mapDialog" else ""):
            return []
        hdr = f"#{i:03d}  {label}  ({len(item)})" if label else f"#{i:03d}  ({len(item)})"
        return [
            CardData(key, (i, j), f"{hdr} .{j:02d}", True, sub, self._model.entry_byte_cost(sub, key))
            for j, sub in enumerate(item)
            if isinstance(sub, str)
        ]
