import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "probes" / "check_state_trust.py"


class StateTrustProbeTests(unittest.TestCase):
    def run_probe(self, *arguments):
        return subprocess.run(
            [sys.executable, str(PROBE), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_same_uid_process_can_mutate_mode_0600_state_and_rollout(self):
        completed = self.run_probe()
        result = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(result["same_uid_state_protected"])
        self.assertFalse(result["same_uid_rollout_protected"])
        self.assertFalse(result["direct_write_qualified"])

    def test_qualification_gate_fails_closed(self):
        completed = self.run_probe("--require-protected")

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertFalse(json.loads(completed.stdout)["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
