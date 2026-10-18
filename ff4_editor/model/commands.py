"""
ff4_editor/model/commands.py
Undo/Redo command objects for PySide6 QUndoStack.
"""

import time
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from ..i18n import tr

if TYPE_CHECKING:
    from .json_model import FF4Model

MERGE_WINDOW_S = 1.5  # consecutive edits of one entry closer than this become one undo step


class EditEntryCommand(QUndoCommand):
    def __init__(
        self, model: "FF4Model", key: str, idx: int | tuple[int, int], old_text: str, new_text: str
    ) -> None:
        label = f"{idx[0]}.{idx[1]}" if isinstance(idx, tuple) else f"{idx}"
        super().__init__(tr("edición de {key} #{label}").format(key=key, label=label))
        self._model = model
        self._key = key
        self._idx = idx
        self._old_text = old_text
        self._new_text = new_text
        self._t = time.monotonic()

    def undo(self) -> None:
        self._model.set_entry(self._key, self._idx, self._old_text)

    def redo(self) -> None:
        self._model.set_entry(self._key, self._idx, self._new_text)

    def id(self) -> int:
        return 1001

    def mergeWith(self, other: QUndoCommand) -> bool:
        if (
            not isinstance(other, EditEntryCommand)
            or other._key != self._key
            or other._idx != self._idx
            or other._t - self._t > MERGE_WINDOW_S
        ):
            return False
        self._new_text = other._new_text
        self._t = other._t
        return True
