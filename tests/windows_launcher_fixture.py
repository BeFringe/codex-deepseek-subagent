"""A real subprocess records only argv and explicitly named noncredential fields."""

import hashlib


def candidate(directory, argument_variable='ARG_LOG', environment_variable='ENV_LOG',
              observed_variable='CODEX_G4_TOOL_CATALOG_RECEIPT'):
    path = directory / 'candidate.py'
    path.write_text(
        'import os, sys\nfrom pathlib import Path\n'
        f"Path(os.environ[{argument_variable!r}]).write_text('\\n'.join(sys.argv[1:]) + '\\n', encoding='utf-8')\n"
        f"if os.environ.get({environment_variable!r}):\n"
        f"    Path(os.environ[{environment_variable!r}]).write_text(os.environ.get({observed_variable!r}, '') + '\\n', encoding='utf-8')\n",
        encoding='utf-8')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()
