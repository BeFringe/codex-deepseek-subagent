"""Exclusive private output: POSIX mode 0600 or a protected Windows DACL."""

import os
from pathlib import Path
import sys


def open_private_output(path):
    if os.name == 'nt':
        hooks = str(Path(__file__).resolve().parents[1] / 'hooks')
        if hooks not in sys.path:
            sys.path.insert(0, hooks)
        from windows_evidence_binding import open_private_output as windows_open

        return windows_open(Path(path))
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
