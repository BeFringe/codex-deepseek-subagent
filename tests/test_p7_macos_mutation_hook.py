import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p7_macos_mutation_hook",
    ROOT / "probes" / "p7_macos_mutation_hook.py",
)
hook = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(hook)


class MacosMutationHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.target = self.root / "foreign.txt"

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_descriptor_write_replaces_all_bytes(self):
        self.target.write_bytes(b"before\n")
        hook._write_exact_regular_file(self.target, b"before\n", b"after\n")
        self.assertEqual(self.target.read_bytes(), b"after\n")

    def test_mismatched_baseline_preserves_existing_bytes(self):
        self.target.write_bytes(b"foreign bytes\n")
        with self.assertRaisesRegex(ValueError, "already modified"):
            hook._write_exact_regular_file(self.target, b"expected\n", b"replacement\n")
        self.assertEqual(self.target.read_bytes(), b"foreign bytes\n")

    def test_symlink_target_is_rejected_without_touching_referent(self):
        referent = self.root / "referent.txt"
        referent.write_bytes(b"referent\n")
        self.target.symlink_to(referent)
        with self.assertRaises(OSError):
            hook._write_exact_regular_file(self.target, b"referent\n", b"replacement\n")
        self.assertEqual(referent.read_bytes(), b"referent\n")

    def test_event_publication_is_exclusive_and_private(self):
        hook._publish_event(self.root, 7, {"schema": 1})
        events = list(self.root.glob("7-*.json"))
        self.assertEqual(len(events), 1)
        self.assertEqual(stat.S_IMODE(events[0].stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
