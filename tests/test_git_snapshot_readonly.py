import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hooks'))
from runtime_guard import collect_git_snapshot


class GitSnapshotReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.file = self.root / 'tracked.txt'
        self.file.write_bytes(b'exact baseline\n')
        self.git('add', 'tracked.txt')
        self.git('commit', '-m', 'baseline')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)

    def test_stat_only_drift_does_not_refresh_the_caller_index(self):
        index = self.root / '.git/index'
        before = index.read_bytes()
        stamp = self.file.stat().st_mtime_ns + 5_000_000_000
        os.utime(self.file, ns=(stamp, stamp))
        result = collect_git_snapshot(str(self.root))
        self.assertEqual(result['git_status_short'], '')
        self.assertFalse(result['index_changed'])
        self.assertEqual(index.read_bytes(), before, 'a read-only snapshot refreshed the caller-owned index')

    def test_no_refresh_still_detects_worktree_and_staged_changes(self):
        self.file.write_bytes(b'staged change\n')
        self.git('add', 'tracked.txt')
        self.file.write_bytes(b'later worktree change\n')
        (self.root / 'untracked.txt').write_bytes(b'new\n')
        index = self.root / '.git/index'
        before = index.read_bytes()
        result = collect_git_snapshot(str(self.root))
        self.assertTrue(result['index_changed'])
        self.assertIn('MM tracked.txt', result['git_status_short'])
        self.assertIn('?? untracked.txt', result['git_status_short'])
        self.assertEqual({p['path'] for p in result['changed_paths']}, {'tracked.txt', 'untracked.txt'})
        self.assertEqual(index.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
