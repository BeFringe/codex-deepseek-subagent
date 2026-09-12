"""Real Windows process exclusion and process-death recovery for schema-v2."""

import os
import errno
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hooks'))
from compatibility_state import StateError, StateStore


ROOT = Path(__file__).resolve().parents[1]
HOLDER = """
import os, sys
sys.path.insert(0, sys.argv[1])
from compatibility_state import StateStore
with StateStore(sys.argv[2]).locked():
    print('LOCKED', flush=True)
    sys.stdin.readline()
    if sys.argv[3] == 'crash':
        os._exit(23)
"""
CONTENDER = """
import msvcrt, os, sys
fd = os.open(sys.argv[1], os.O_RDWR)
try:
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        sys.exit(19)
finally:
    os.close(fd)
"""


@unittest.skipUnless(os.name == 'nt', 'requires native Windows byte-range locks')
class WindowsStateLockTests(unittest.TestCase):
    def test_failed_acquisition_never_enters_authority_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            for code in (errno.EIO, errno.EACCES):
                store = StateStore(Path(temporary) / str(code))
                marker = store.root / 'must-not-be-written'
                with self.subTest(errno=code), patch('compatibility_state.msvcrt.locking',
                        side_effect=OSError(code, 'simulated acquisition failure')), \
                        patch('compatibility_state.time.monotonic', side_effect=[0, 11]):
                    with self.assertRaises(StateError):
                        with store.locked():
                            marker.write_text('unauthorized', encoding='utf-8')
                self.assertFalse(marker.exists())
                # Closing the failed descriptor must allow a subsequent real acquisition.
                with store.locked():
                    self.assertFalse(marker.exists())

    def exercise_release(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / 'state'
            holder = subprocess.Popen(
                [sys.executable, '-c', HOLDER, str(ROOT / 'hooks'), str(state), mode],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            try:
                ready = queue.Queue()
                reader = threading.Thread(target=lambda: ready.put(holder.stdout.readline()), daemon=True)
                reader.start()
                self.assertEqual(ready.get(timeout=15).strip(), 'LOCKED')
                reader.join(timeout=1)
                lock = state / '.compatibility-state.lock'
                blocked = subprocess.run(
                    [sys.executable, '-c', CONTENDER, str(lock)], timeout=15,
                    capture_output=True, text=True,
                )
                self.assertEqual(blocked.returncode, 19, blocked.stderr)
                _, stderr = holder.communicate('\n', timeout=15)
                self.assertEqual(holder.returncode, 23 if mode == 'crash' else 0, stderr)
                recovered = subprocess.run(
                    [sys.executable, '-c', HOLDER, str(ROOT / 'hooks'), str(state), 'normal'],
                    input='\n', capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                self.assertEqual(recovered.stdout.strip(), 'LOCKED')
                self.assertEqual(lock.read_bytes(), b'')
            finally:
                if holder.poll() is None:
                    holder.kill()
                holder.communicate(timeout=15)

    def test_exclusion_and_normal_release(self):
        self.exercise_release('normal')

    def test_os_exit_releases_kernel_lock(self):
        self.exercise_release('crash')


if __name__ == '__main__':
    unittest.main()
