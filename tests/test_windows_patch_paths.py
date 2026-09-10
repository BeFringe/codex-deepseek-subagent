"""Native Windows path spelling must preserve exact writer ownership."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hooks'))
from writer_lease_guard import WriterLeaseError, extract_apply_patch_paths, normalize_patch_paths


def patch_for(path):
    return '*** Begin Patch\n*** Add File: ' + path + '\n+probe\n*** End Patch'


@unittest.skipUnless(os.name == 'nt', 'requires native Windows path resolution')
class WindowsPatchPathTests(unittest.TestCase):
    def test_native_separators_bind_to_the_same_owned_relative_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'repository'
            root.mkdir()
            target = root / 'owned' / 'result.txt'
            for spelling in (str(target), target.as_posix(), 'owned\\result.txt'):
                raw = extract_apply_patch_paths(patch_for(spelling))
                self.assertEqual(normalize_patch_paths(raw, cwd=str(root), root=str(root)),
                                 ['owned/result.txt'])
            with self.assertRaises(WriterLeaseError):
                normalize_patch_paths([str(target), target.as_posix()], cwd=str(root), root=str(root))
            with self.assertRaises(WriterLeaseError):
                normalize_patch_paths(['owned/result.txt', 'OWNED/RESULT.TXT'],
                                      cwd=str(root), root=str(root))
            with self.assertRaises(WriterLeaseError):
                normalize_patch_paths(['..\\outside.txt'], cwd=str(root), root=str(root))

    def test_windows_device_stream_and_alias_spellings_fail_closed(self):
        for spelling in ('C:relative.txt', 'owned\\result.txt:stream',
                         '\\\\?\\C:\\owned\\result.txt', '\\\\.\\NUL',
                         'owned\\NUL.txt', 'NUL\\result.txt',
                         'owned\\result.txt.', 'owned \\result.txt'):
            with self.subTest(path=spelling), self.assertRaises(WriterLeaseError):
                extract_apply_patch_paths(patch_for(spelling))


if __name__ == '__main__':
    unittest.main()
