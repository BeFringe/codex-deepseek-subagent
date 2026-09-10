import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hooks"))


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
        if os.name == "nt":
            import _winapi

            # A junction is a native directory reparse point and does not need
            # the symlink privilege. Exercise the real Windows no-follow path.
            _winapi.CreateJunction(str(actual), str(self.root / "evidence"))
        else:
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
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                from windows_evidence_binding import kernel

                kernel.SetFileInformationByHandle.argtypes = [
                    wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
                kernel.SetFileInformationByHandle.restype = wintypes.BOOL
                handle = kernel.CreateFileW(str(output), 0x10000, 7, None, 3, 0, None)
                if handle == wintypes.HANDLE(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    # FileDispositionInfoEx with DELETE | POSIX_SEMANTICS
                    # removes the name while the original evidence fd stays open.
                    flags = wintypes.DWORD(3)
                    if not kernel.SetFileInformationByHandle(
                            handle, 21, ctypes.byref(flags), ctypes.sizeof(flags)):
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    kernel.CloseHandle(handle)
                output.write_text("replacement", encoding="utf-8")
            else:
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

    @unittest.skipUnless(os.name == "nt", "requires Windows directory handles and junctions")
    def test_windows_directory_replacement_is_blocked_or_detected(self):
        import _winapi

        outside = self.root / "outside"
        outside.mkdir()
        renamed = []

        def replace_directory(descriptor):
            os.write(descriptor, b"original")
            (self.root / "evidence").rename(self.root / "original-evidence")
            renamed.append(True)
            _winapi.CreateJunction(str(outside), str(self.root / "evidence"))

        with self.assertRaises(evidence_binding.EvidenceBindingViolation) as raised:
            evidence_binding.run_bound_evidence(
                self.binding,
                executed_root=str(self.root),
                hashed_root=str(self.root),
                source_identity=self.source,
                expensive_runner=replace_directory,
            )
        if renamed:
            self.assertIn("reparse point", str(raised.exception))
        else:
            # Windows may refuse the directory rename while its child is open.
            # Verify that specific native denial and the preserved original.
            self.assertIsInstance(raised.exception.__cause__, PermissionError)
            self.assertIn(raised.exception.__cause__.winerror, (5, 32))
            self.assertEqual((self.root / "evidence" / "result.json").read_bytes(), b"original")
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
