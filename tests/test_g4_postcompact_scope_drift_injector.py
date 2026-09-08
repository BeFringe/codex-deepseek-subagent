import contextlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "inject_g4_postcompact_scope_drift.py"


def load_module():
    spec = importlib.util.spec_from_file_location("g4_postcompact_drift_injector", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


injector = load_module()


class FakeStore:
    def __init__(self, root: Path):
        self.root = root
        self.lock_held = False

    @contextlib.contextmanager
    def locked(self):
        self.lock_held = True
        try:
            yield
        finally:
            self.lock_held = False

    def _validated_envelope(self, path: Path):
        if not self.lock_held:
            raise AssertionError("state read was not serialized")
        return json.loads(path.read_text(encoding="utf-8"))


class G4PostcompactScopeDriftInjectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-postcompact-drift-fixture-", dir="/private/tmp"
        )
        self.root = Path(self.directory.name).resolve()
        self.state = self.root.parent / f"{self.root.name}.state"
        self.output = self.root.parent / f"{self.root.name}.report.json"
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Fixture"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "fixture@example.invalid"],
            check=True,
        )
        (self.root / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "baseline.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "baseline"],
            check=True,
            capture_output=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.task_name = "g4_postcompact_drift_fixture"
        self.assignment_id = "11111111-1111-4111-8111-111111111111"
        self.envelope = {
            "schema": 2,
            "assignment": "fixture assignment",
            "capsule": {
                "assignment_id": self.assignment_id,
                "handoff_id": "22222222-2222-4222-8222-222222222222",
                "runtime_session_id": "runtime-session",
                "requested_task_name": self.task_name,
                "canonical_agent_path": f"/root/{self.task_name}",
                "assignment_mutation_mode": "read_only",
                "owned_paths": [],
                "excluded_paths": [],
                "git_authority": {
                    "stage": False,
                    "commit": False,
                    "branch": False,
                    "push": False,
                },
                "root": {
                    "path": str(self.root),
                    "branch": "main",
                    "base_commit": self.head,
                },
            },
            "binding": {
                "child_thread_id": "child-thread",
                "canonical_agent_path": f"/root/{self.task_name}",
            },
            "runtime": {
                "recovery_count": 1,
                "context_lost": False,
                "first_git_attested_at": "2026-09-08T00:00:00+00:00",
            },
        }
        active = self.state / "active"
        active.mkdir(parents=True)
        (active / f"{self.assignment_id}.json").write_text(
            json.dumps(self.envelope), encoding="utf-8"
        )
        self.store = FakeStore(self.state)

    def tearDown(self):
        if self.output.exists():
            self.output.unlink()
        if self.state.exists():
            for path in sorted(self.state.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            self.state.rmdir()
        self.directory.cleanup()

    def test_injection_is_lock_serialized_exact_and_not_child_attributed(self):
        result = injector.inject_if_recovered(self.store, self.root, self.task_name)

        target = self.root / injector.TARGET_NAME
        self.assertIsNotNone(result)
        self.assertEqual(target.read_bytes(), injector.TARGET_CONTENT)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertTrue(result["state_lock_held_during_injection"])
        self.assertEqual(result["recovery_count"], 1)
        self.assertEqual(result["target_relative_path"], injector.TARGET_NAME)
        self.assertEqual(result["before_snapshot"]["changed_paths"], [])
        self.assertEqual(
            result["after_snapshot"]["changed_paths"],
            [
                {
                    "path": injector.TARGET_NAME,
                    "kind": "file",
                    "sha256": injector.sha256_bytes(injector.TARGET_CONTENT),
                }
            ],
        )
        self.assertFalse(result["child_mutation_authorized"])
        self.assertFalse(result["injected_bytes_attributed_to_child"])

    def test_no_injection_before_recovery_epoch(self):
        self.envelope["runtime"]["recovery_count"] = 0
        active = self.state / "active" / f"{self.assignment_id}.json"
        active.write_text(json.dumps(self.envelope), encoding="utf-8")

        result = injector.inject_if_recovered(self.store, self.root, self.task_name)

        self.assertIsNone(result)
        self.assertFalse((self.root / injector.TARGET_NAME).exists())

    def test_write_or_path_authority_and_output_reuse_fail_closed(self):
        self.envelope["capsule"]["owned_paths"] = [injector.TARGET_NAME]
        active = self.state / "active" / f"{self.assignment_id}.json"
        active.write_text(json.dumps(self.envelope), encoding="utf-8")
        with self.assertRaisesRegex(injector.ProbeError, "empty path authority"):
            injector.inject_if_recovered(self.store, self.root, self.task_name)

        injector.write_report(self.output, {"schema": 1})
        with self.assertRaises(FileExistsError):
            injector.write_report(self.output, {"schema": 1})


if __name__ == "__main__":
    unittest.main()
