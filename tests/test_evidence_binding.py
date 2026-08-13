import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evidence_binding = load_module(
    "evidence_binding", REPO / "hooks" / "evidence_binding.py"
)


class EvidenceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        (self.root / "evidence").mkdir()
        self.source = {"kind": "git_commit", "value": "a" * 40}
        self.binding = {
            "executed_root": str(self.root),
            "hashed_root": str(self.root),
            "source_identity": self.source,
            "canonical_output": "evidence/result.json",
            "no_follow_dirfd_walk": True,
            "terminal_regular_file_reproof": True,
            "preflight_before_expensive_execution": True,
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_exact_authority_is_preflighted_before_expensive_execution(self):
        ran = []

        result = evidence_binding.run_bound_evidence(
            self.binding,
            executed_root=str(self.root),
            hashed_root=str(self.root),
            source_identity=self.source,
            expensive_runner=lambda descriptor: (ran.append(True), os.write(descriptor, b"{}\n")),
        )

        self.assertEqual(ran, [True])
        self.assertTrue(result["terminal_identity_reproved"])

    def test_checkout_mismatch_blocks_before_expensive_execution(self):
        ran = []
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(
                evidence_binding.EvidenceBindingViolation, "not the same authority"
            ):
                evidence_binding.run_bound_evidence(
                    self.binding,
                    executed_root=str(self.root),
                    hashed_root=other,
                    source_identity=self.source,
                    expensive_runner=lambda descriptor: ran.append(True),
                )
        self.assertEqual(ran, [])

    def test_symlinked_directory_is_rejected_by_no_follow_walk(self):
        actual = self.root / "actual"
        actual.mkdir()
        (self.root / "evidence").rmdir()
        (self.root / "evidence").symlink_to(actual, target_is_directory=True)

        with self.assertRaisesRegex(
            evidence_binding.EvidenceBindingViolation, "no-follow output walk failed"
        ):
            evidence_binding.run_bound_evidence(
                self.binding,
                executed_root=str(self.root),
                hashed_root=str(self.root),
                source_identity=self.source,
                expensive_runner=lambda descriptor: None,
            )

    def test_terminal_replacement_is_detected_after_runner(self):
        output = self.root / "evidence" / "result.json"

        def replace_terminal(descriptor):
            os.write(descriptor, b"original")
            output.unlink()
            output.write_text("replacement", encoding="utf-8")

        with self.assertRaisesRegex(
            evidence_binding.EvidenceBindingViolation, "terminal identity changed"
        ):
            evidence_binding.run_bound_evidence(
                self.binding,
                executed_root=str(self.root),
                hashed_root=str(self.root),
                source_identity=self.source,
                expensive_runner=replace_terminal,
            )


if __name__ == "__main__":
    unittest.main()
