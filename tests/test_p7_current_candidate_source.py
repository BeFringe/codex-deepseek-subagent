import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
import p7_current_candidate_source as source


class CompleteSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        self.git('config', 'core.autocrlf', 'true')
        (self.root / 'tracked.rs').write_bytes(b'first\nsecond\n')
        self.git('add', 'tracked.rs')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-qm', 'fixture baseline')
        self.hashes = {}
        for name in source.SOURCE_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = ('synthetic source for identity contract: ' + name + '\n').encode()
            path.write_bytes(data)
            self.hashes[name] = hashlib.sha256(data).hexdigest()
        self.patch = mock.patch.dict(source.SOURCE_FILES, self.hashes, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        tree_patch = mock.patch.object(source, 'SOURCE_TREE', source.raw_source_tree(self.root))
        tree_patch.start()
        self.addCleanup(tree_patch.stop)
        self.build = {'patch_sha256': source.CUMULATIVE, 'final_patch_sha256': source.FINAL_PATCH,
                      'source_chain_receipt_sha256': source.SOURCE_RECEIPT,
                      'source_tree': source.SOURCE_TREE,
                      'complete_source_patch_sha256': source.COMPLETE_REPLAY,
                      'complete_source_receipt_sha256': source.COMPLETE_SOURCE_RECEIPT,
                      'additional_source_files_sha256': dict(self.hashes)}

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True).stdout

    def test_crlf_tracked_bytes_cannot_hide_behind_normalized_diff(self):
        before_index = (self.root / '.git/index').read_bytes()
        source.verify_current_source(ROOT, self.root, self.build)
        (self.root / 'tracked.rs').write_bytes(b'first\r\nsecond\r\n')
        self.assertEqual(self.git('diff', 'HEAD', '--', 'tracked.rs'), b'')
        with self.assertRaisesRegex(ValueError, 'complete raw source tree drift'):
            source.verify_current_source(ROOT, self.root, self.build)
        self.assertEqual((self.root / '.git/index').read_bytes(), before_index)

    def test_unchanged_tracked_diff_cannot_hide_new_file_mutation(self):
        source.verify_current_source(ROOT, self.root, self.build)
        (self.root / next(iter(self.hashes))).write_bytes(b'changed after build')
        with self.assertRaisesRegex(ValueError, 'source files absent from canonical tracked diff changed'):
            source.verify_current_source(ROOT, self.root, self.build)

    def test_extra_untracked_source_is_rejected(self):
        (self.root / 'extra.rs').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'unexpected untracked build source'):
            source.verify_current_source(ROOT, self.root, self.build)

    def test_other_build_tree_does_not_share_this_source_identity(self):
        self.build['source_tree'] = 'a' * 40
        with self.assertRaisesRegex(ValueError, 'complete final source build identity'):
            source.verify_current_source(ROOT, self.root, self.build)


if __name__ == '__main__':
    unittest.main()
