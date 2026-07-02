"""
ff4_editor/model/commands.py
Undo/Redo command objects for PySide6 QUndoStack.
"""
from PySide6.QtGui import QUndoCommand

class EditEntryCommand(QUndoCommand):
    def __init__(self, model, key: str, idx, old_text: str, new_text: str):
        super().__init__(f"Edit {key}[{idx}]")
        self._model = model
        self._key = key
        self._idx = idx
        self._old_text = old_text
        self._new_text = new_text

    def undo(self):
        self._model.set_entry(self._key, self._idx, self._old_text)

    def redo(self):
        self._model.set_entry(self._key, self._idx, self._new_text)