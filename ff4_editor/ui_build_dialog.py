"""
ff4_editor/ui_build_dialog.py
Ventana de compilacion: ejecuta `make ff4-es` en el directorio del JSON abierto
y muestra la salida en vivo (stdout + stderr).
"""

import codecs
import re

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .i18n import tr

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class BuildDialog(QDialog):
    def __init__(self, workdir: str, command: str = "make", args=("ff4-es",), parent=None):
        super().__init__(parent)
        self._command = command
        self._args = list(args)
        self.setWindowTitle(tr("Compilar"))
        self.resize(900, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        lay = QVBoxLayout(self)
        self._cwd_lbl = QLabel(f"{workdir}$ {command} {' '.join(self._args)}")
        self._cwd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._cwd_lbl)

        self._out = QPlainTextEdit()
        self._out.setReadOnly(True)
        self._out.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._out.setMaximumBlockCount(50000)
        f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        f.setPointSize(10)
        self._out.setFont(f)
        lay.addWidget(self._out, 1)

        row = QHBoxLayout()
        self._status = QLabel("")
        row.addWidget(self._status, 1)
        self._rerun_btn = QPushButton(tr("Repetir"))
        self._rerun_btn.clicked.connect(self.start)
        self._stop_btn = QPushButton(tr("Detener"))
        self._stop_btn.clicked.connect(self._stop)
        self._close_btn = QPushButton(tr("Cerrar"))
        self._close_btn.clicked.connect(self.close)
        for b in (self._rerun_btn, self._stop_btn, self._close_btn):
            row.addWidget(b)
        lay.addLayout(row)

        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(workdir)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "dumb")
        env.insert("PYTHONUNBUFFERED", "1")
        self._proc.setProcessEnvironment(env)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)

    def start(self):
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._out.clear()
        self._decoder.reset()
        self._append(f"$ {self._command} {' '.join(self._args)}\n")
        self._status.setText(tr("Compilando…"))
        self._rerun_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._proc.start(self._command, self._args)

    def _append(self, text: str):
        text = _ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
        bar = self._out.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        cur = self._out.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(text)
        if at_end:
            bar.setValue(bar.maximum())

    def _on_output(self):
        self._append(self._decoder.decode(self._proc.readAllStandardOutput().data()))

    def _on_finished(self, code, status):
        self._on_output()
        ok = status == QProcess.ExitStatus.NormalExit and code == 0
        if ok:
            self._append(tr("\n[OK] terminado con codigo {code}\n").format(code=code))
            self._status.setText(tr("Compilacion correcta"))
        else:
            self._append(tr("\n[ERROR] terminado con codigo {code}\n").format(code=code))
            self._status.setText(tr("Fallo (codigo {code})").format(code=code))
        self._rerun_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def _on_error(self, err):
        if err == QProcess.ProcessError.FailedToStart:
            self._append(
                tr("\nNo se pudo ejecutar '{cmd}' (¿esta instalado y en el PATH?)\n").format(
                    cmd=self._command
                )
            )
            self._status.setText(tr("No se pudo iniciar"))
            self._rerun_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)

    def _stop(self):
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.terminate()
            if not self._proc.waitForFinished(1500):
                self._proc.kill()

    def closeEvent(self, ev):
        self._stop()
        super().closeEvent(ev)
