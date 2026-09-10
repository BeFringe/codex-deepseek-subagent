import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from private_output import open_private_output
from p7_windows_acl import run_file_acl


@unittest.skipUnless(os.name == 'nt', 'requires native Windows DACL creation')
class WindowsPrivateOutputTests(unittest.TestCase):
    def test_creation_does_not_inherit_a_broad_parent_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            icacls = Path(os.environ['SystemRoot']) / 'System32' / 'icacls.exe'
            subprocess.run([str(icacls), str(root), '/grant', '*S-1-5-11:(OI)(CI)M'],
                           check=True, capture_output=True, timeout=15)
            output = root / 'private.json'
            with os.fdopen(open_private_output(output), 'wb') as stream:
                stream.write(b'original')
            self.assertTrue(run_file_acl(output)['protected'])
            with self.assertRaises(OSError):
                open_private_output(output)
            self.assertEqual(output.read_bytes(), b'original')

    def test_device_stream_and_trailing_alias_are_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('NUL.txt', 'result.txt:stream', 'result.txt.'):
                with self.subTest(name=name), self.assertRaises(OSError):
                    open_private_output(root / name)
            self.assertEqual(list(root.iterdir()), [])
