"""
ff4_editor/errors.py
Standardized error handling for the FF4 editor.
Provides consistent error reporting, logging, and user feedback.
"""

import json
import logging
import os
import shutil
import tempfile
from enum import IntEnum

from .i18n import tr

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
)

logger = logging.getLogger("ff4_editor")


class ErrorSeverity(IntEnum):
    """Error severity levels for consistent handling."""

    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


class FF4Error(Exception):
    """Base exception for FF4 editor errors."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        recoverable: bool = True,
        details: str = "",
    ):
        super().__init__(message)
        self.severity = severity
        self.recoverable = recoverable
        self.details = details


class FileSaveError(FF4Error):
    """Error writing a file (JSON data, configuration...)."""

    def __init__(self, path: str, reason: str, severity: ErrorSeverity = ErrorSeverity.ERROR):
        super().__init__(
            tr("No se pudo guardar {path}: {reason}").format(path=path, reason=reason),
            severity,
            details=f"Path: {path}",
        )


class FileLoadError(FF4Error):
    """Error loading a file (JSON, LNK, PNG, etc.)."""

    def __init__(self, path: str, reason: str, severity: ErrorSeverity = ErrorSeverity.ERROR):
        super().__init__(
            tr("No se pudo cargar {path}: {reason}").format(path=path, reason=reason),
            severity,
            details=f"Path: {path}",
        )


def validate_file_exists(path: str, description: str | None = None) -> None:
    """Raise FileLoadError if `path` is not an existing file."""
    if not os.path.isfile(path):
        raise FileLoadError(
            path, tr("{description}: no encontrado").format(description=description or tr("Archivo"))
        )


def safe_json_load(path: str, description: str | None = None) -> dict:
    """Load JSON from `path`; every failure surfaces as FileLoadError.
    Reads with utf-8-sig so a BOM at the start of the file is accepted."""
    validate_file_exists(path, description or tr("Archivo JSON"))
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise FileLoadError(path, tr("JSON inválido: {error}").format(error=e)) from e
    except (OSError, UnicodeDecodeError) as e:
        raise FileLoadError(path, str(e)) from e


def safe_json_save(path: str, data: dict, description: str = "JSON file", backup: bool = True) -> None:
    """Atomically save JSON: write to a temp file in the same directory, fsync, then
    os.replace over the target.  The previous version is kept as '<path>.bak'.
    Format matches `make rip` output (indent=2, no ASCII escaping, no trailing newline)
    so saving an untouched file produces no git diff.
    Raises FileSaveError on any failure; the original file is left untouched."""
    tmp = None
    try:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if backup and os.path.isfile(path):
            shutil.copy2(path, path + ".bak")
        os.replace(tmp, path)
        tmp = None
    except (OSError, TypeError, ValueError) as e:
        logger.error(f"Failed to save {description} to {path}: {e}")
        raise FileSaveError(path, str(e)) from e
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                logger.warning(f"Could not remove temporary file {tmp}")
