import os
from pathlib import Path
import sys


def assert_private_output(test, path):
    if os.name == 'nt':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
        from p7_windows_acl import run_file_acl

        test.assertTrue(run_file_acl(path)['protected'])
    else:
        test.assertEqual(path.stat().st_mode & 0o777, 0o600)
