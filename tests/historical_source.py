"""Validate historical receipts against their preserved source, not today's file."""

import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION_BASE = '785b945d46a9a8879f659a428ff0a03d940cf7a1'


def historical_sha256(path):
    relative = path.relative_to(ROOT).as_posix()
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                   QUALIFICATION_BASE + ':' + relative])
    return hashlib.sha256(raw).hexdigest()
