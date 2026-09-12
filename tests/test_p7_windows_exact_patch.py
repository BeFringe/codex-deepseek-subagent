from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from adjudicate_g4_sibling_admission_live import AdjudicationError
from verify_p7_windows_mutation_outcome import verify_exact_single_file_patch


class ExactNativePatchPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(strict=True)
        (self.root / 'qualified.txt').write_bytes(b'G4_CHILD_WRITE_QUALIFIED\n')
        (self.root / 'foreign.txt').write_bytes(b'foreign\n')

    def patch(self, path, body='+G4_CHILD_WRITE_QUALIFIED'):
        return f'*** Begin Patch\n*** Add File: {path}\n{body}\n*** End Patch\n'

    def verify(self, patch):
        return verify_exact_single_file_patch(patch, self.root, 'qualified.txt', 'Add',
                                              '+G4_CHILD_WRITE_QUALIFIED')

    def test_exact_basename_and_absolute_header_bind_the_same_target(self):
        for path in ('qualified.txt', str(self.root / 'qualified.txt')):
            with self.subTest(path=path):
                self.assertEqual(self.verify(self.patch(path)), self.root / 'qualified.txt')

    def test_aliases_drive_relative_and_foreign_headers_are_rejected(self):
        for path in ('../qualified.txt', './qualified.txt', 'sub/../qualified.txt',
                     'C:qualified.txt', 'foreign.txt', str(self.root / 'foreign.txt')):
            with self.subTest(path=path), self.assertRaises(AdjudicationError):
                self.verify(self.patch(path))

    def test_extra_operation_or_different_bytes_are_rejected(self):
        for body in ('+wrong bytes', '+G4_CHILD_WRITE_QUALIFIED\n+',
                     '+G4_CHILD_WRITE_QUALIFIED\n*** Add File: foreign.txt\n+changed'):
            with self.subTest(body=body), self.assertRaises(AdjudicationError):
                self.verify(self.patch('qualified.txt', body))


if __name__ == '__main__':
    unittest.main()
