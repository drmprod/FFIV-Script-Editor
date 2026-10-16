"""
ff4_editor/ui_build_dialog.py
Ventana de compilacion: ejecuta `make ff4-es` en el directorio del JSON abierto
y muestra la salida en vivo (stdout + stderr).
"""

import re

from PySide6.QtCore    import Qt, QProcess, QProcessEnvironment
from PySide6.QtGui     import QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QLabel,
)

_ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


class BuildDialog(QDialog):
    def __init__(self, workdir: str, command: str = "make", args=("ff4-es",), parent=None):
        super().__init__(parent)
        self._command = command
        self._args = list(args)
        self.setWindowTitle("Compilar")
        self.resize(900, 560)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        lay = QVBoxLayout(self)
        self._cwd_lbl = QLabel(f"{workdir}$ {command} {' '.join(self._args)}")
        self._cwd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self._cwd_lbl)

        self._out = QPlainTextEdit()
        self._out.setReadOnly(True)
        self._out.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._out.setMaximumBlockCount(50000)
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        f.setPointSize(10)
        self._out.setFont(f)
        lay.addWidget(self._out, 1)

        row = QHBoxLayout()
        self._status = QLabel("")
        row.addWidget(self._status, 1)
        self._rerun_btn = QPushButton("Repetir")
        self._rerun_btn.clicked.connect(self.start)
        self._stop_btn = QPushButton("Detener")
        self._stop_btn.clicked.connect(self._stop)
        self._close_btn = QPushButton("Cerrar")
        self._close_btn.clicked.connect(self.close)
        for b in (self._rerun_btn, self._stop_btn, self._close_btn):
            row.addWidget(b)
        lay.addLayout(row)

        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(workdir)
        self._proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "dumb")
        env.insert("PYTHONUNBUFFERED", "1")
        self._proc.setProcessEnvironment(env)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)

    def start(self):
        if self._proc.state() != QProcess.NotRunning:
            return
        self._out.clear()
        self._append(f"$ {self._command} {' '.join(self._args)}\n")
        self._status.setText("Compilando…")
        self._rerun_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._proc.start(self._command, self._args)

    def _append(self, text: str):
        text = _ANSI.sub('', text).replace('\r\n', '\n').replace('\r', '\n')
        bar = self._out.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        cur = self._out.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText(text)
        if at_end:
            bar.setValue(bar.maximum())

    def _on_output(self):
        self._append(bytes(self._proc.readAllStandardOutput()).decode('utf-8', 'replace'))

    def _on_finished(self, code, status):
        self._on_output()
        ok = (status == QProcess.NormalExit and code == 0)
        self._append(f"\n[{'OK' if ok else 'ERROR'}] terminado con codigo {code}\n")
        self._status.setText("Compilacion correcta" if ok else f"Fallo (codigo {code})")
        self._rerun_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def _on_error(self, err):
        if err == QProcess.FailedToStart:
            self._append(f"\nNo se pudo ejecutar '{self._command}' "
                         f"(¿esta instalado y en el PATH?)\n")
            self._status.setText("No se pudo iniciar")
            self._rerun_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)

    def _stop(self):
        if self._proc.state() != QProcess.NotRunning:
            self._proc.terminate()
            if not self._proc.waitForFinished(1500):
                self._proc.kill()

    def closeEvent(self, ev):
        self._stop()
        super().closeEvent(ev)
