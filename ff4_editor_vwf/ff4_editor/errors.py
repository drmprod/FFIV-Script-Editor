"""
ff4_editor/errors.py
Standardized error handling for the FF4 editor.
Provides consistent error reporting, logging, and user feedback.
"""

import logging
from enum import IntEnum


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger('ff4_editor')


class ErrorSeverity(IntEnum):
    """Error severity levels for consistent handling."""
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


class FF4Error(Exception):
    """Base exception for FF4 editor errors."""
    
    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.ERROR, 
                 recoverable: bool = True, details: str = ''):
        super().__init__(message)
        self.severity = severity
        self.recoverable = recoverable
        self.details = details


class FileLoadError(FF4Error):
    """Error loading a file (JSON, LNK, PNG, etc.)."""
    def __init__(self, path: str, reason: str, severity: ErrorSeverity = ErrorSeverity.ERROR):
        super().__init__(f"Failed to load {path}: {reason}", severity, 
                         details=f"Path: {path}")


def validate_file_exists(path: str, description: str = 'File') -> bool:
    """Validate that a file exists, raising FileLoadError if not."""
    import os
    if not os.path.isfile(path):
        raise FileLoadError(path, f"{description} not found")
    return True


def safe_json_load(path: str, description: str = 'JSON file') -> dict:
    """Safely load JSON from file with consistent error handling.
    Reads with utf-8-sig so a BOM at the start of the file is accepted."""
    import json
    try:
        validate_file_exists(path, description)
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise FileLoadError(path, f"Invalid JSON: {e}")
    except Exception as e:
        raise FileLoadError(path, str(e))


def safe_json_save(path: str, data: dict, description: str = 'JSON file',
                   backup: bool = True) -> bool:
    """Atomically save JSON: write to a temp file in the same directory, fsync, then
    os.replace over the target.  The previous version is kept as '<path>.bak'.
    Format matches `make rip` output (indent=2, no ASCII escaping, no trailing newline)
    so saving an untouched file produces no git diff."""
    import json
    import os
    import shutil
    import tempfile
    tmp = None
    try:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.' + os.path.basename(path) + '.',
                                   suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if backup and os.path.isfile(path):
            shutil.copy2(path, path + '.bak')
        os.replace(tmp, path)
        tmp = None
        return True
    except Exception as e:
        logger.error(f"Failed to save {description} to {path}: {e}")
        return False
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

