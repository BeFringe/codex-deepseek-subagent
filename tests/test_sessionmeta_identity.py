import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "probes" / "check_sessionmeta_identity.py"
SPEC = importlib.util.spec_from_file_location("check_sessionmeta_identity", SCRIPT)
identity_probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(identity_probe)


def uuid7(number):
    return f"019d0000-0000-7000-8000-{number:012x}"


RUNTIME_SESSION = uuid7(1)
ROOT_THREAD = RUNTIME_SESSION
NESTED_PARENTS = {
    "nested_serial": uuid7(2),
    "nested_concurrent": uuid7(3),
}


def session_meta_line(payload):
    return json.dumps(
        {
            "timestamp": "2026-08-16T00:00:00.070Z",
            "ordinal": 0,
            "type": "session_meta",
            "payload": payload,
        },
        separators=(",", ":"),
    ) + "\n"


def thread_spawn(parent_id, depth, path, role):
    return {
        "subagent": {
            "thread_spawn": {
                "parent_thread_id": parent_id,
                "depth": depth,
                "agent_path": path,
                "agent_nickname": None,
                "agent_role": role,
            }
        }
    }


def parent_meta(parent_id, nested, root, parent_path):
    payload = {
        "session_id": RUNTIME_SESSION,
        "id": parent_id,
        "timestamp": "2026-08-16T00:00:00Z",
        "cwd": str(root),
        "originator": "fixture",
        "cli_version": identity_probe.PINNED_CODEX_VERSION,
        "source": "vscode",
        "model_provider": "openai",
    }
    if nested:
        payload.update(
            {
                "parent_thread_id": ROOT_THREAD,
                "agent_role": "explorer",
                "agent_path": parent_path,
                "source": thread_spawn(ROOT_THREAD, 1, parent_path, "explorer"),
            }
        )
    return payload


def observation(root, kind, index):
    nested = kind.startswith("nested")
    concurrent = kind.endswith("concurrent")
    parent_id = NESTED_PARENTS[kind] if nested else ROOT_THREAD
    requested = f"{kind}_{index}"
    parent_path = f"/root/outer_{kind}" if nested else "/root"
    canonical = f"{parent_path}/{requested}"
    child_id = uuid7(100 + sorted(identity_probe.CASE_KINDS).index(kind) * 2 + index)
    role = "explorer"
    parent_rollout_path = root / f"{parent_id}.jsonl"
    child_rollout_path = root / f"{child_id}.jsonl"
    capture = {
        "session_id": RUNTIME_SESSION,
        "turn_id": f"parent-turn-{kind}-{index}",
        "transcript_path": str(parent_rollout_path),
        "cwd": str(root),
        "hook_event_name": "PreToolUse",
        "model": "gpt-fixture",
        "permission_mode": "read-only",
        "tool_name": "spawn_agent",
        "tool_input": {
            "message": f"read-only fixture {kind} {index}",
            "task_name": requested,
            "agent_type": role,
            "fork_turns": "none",
        },
        "tool_use_id": f"spawn-tool-{kind}-{index}",
    }
    if nested:
        capture.update({"agent_id": parent_id, "agent_type": role})
    child_payload = {
        "session_id": RUNTIME_SESSION,
        "id": child_id,
        "parent_thread_id": parent_id,
        "timestamp": "2026-08-16T00:00:00Z",
        "cwd": str(root),
        "originator": "fixture",
        "cli_version": identity_probe.PINNED_CODEX_VERSION,
        "source": thread_spawn(parent_id, 2 if nested else 1, canonical, role),
        "agent_role": role,
        "agent_path": canonical,
        "model_provider": "openai",
    }
    return {
        "case_id": f"{kind}-{index}",
        "case_kind": kind,
        "cohort_id": f"cohort-{kind}" if concurrent else None,
        "capture_hook": capture,
        "spawn_result": {"task_name": canonical, "nickname": None},
        "start_hook": {
            "session_id": RUNTIME_SESSION,
            "turn_id": f"child-turn-{kind}-{index}",
            "transcript_path": str(child_rollout_path),
            "cwd": str(root),
            "hook_event_name": "SubagentStart",
            "model": "gpt-fixture",
            "permission_mode": "read-only",
            "agent_id": child_id,
            "agent_type": role,
        },
        "parent_rollout": {
            "path": str(parent_rollout_path),
            "session_meta_line": session_meta_line(
                parent_meta(parent_id, nested, root, parent_path)
            ),
        },
        "child_rollout": {
            "path": str(child_rollout_path),
            "session_meta_line": session_meta_line(child_payload),
        },
    }


class SessionMetaIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.bundle = {
            "schema": 1,
            "codex_version": identity_probe.PINNED_CODEX_VERSION,
            "source_commit": identity_probe.PINNED_SOURCE_COMMIT,
            "evidence_origin": "provider_free_fixture",
            "observations": [
                observation(self.root, kind, index)
                for kind in sorted(identity_probe.CASE_KINDS)
                for index in range(2)
            ],
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def assert_invalid(self, bundle, pattern):
        with self.assertRaisesRegex(identity_probe.IdentityEvidenceError, pattern):
            identity_probe.validate_bundle(bundle)

    def test_exact_root_nested_serial_concurrent_matrix_passes_mechanically(self):
        result = identity_probe.validate_bundle(self.bundle)

        self.assertTrue(result["mechanically_exact"])
        self.assertTrue(result["matrix_complete"])
        self.assertEqual(result["observation_count"], 8)
        self.assertEqual(set(result["case_counts"]), identity_probe.CASE_KINDS)
        self.assertEqual(result["adjudication_authority"], "none")
        self.assertFalse(result["p2_live_qualified"])

    def test_exact_matrix_accepts_windows_absolute_transcript_paths(self):
        bundle = copy.deepcopy(self.bundle)
        for index, item in enumerate(bundle["observations"]):
            parent_path = rf"C:\Codex\rollouts\parent-{index}.jsonl"
            child_path = rf"C:\Codex\rollouts\child-{index}.jsonl"
            cwd = r"C:\work\compatibility-probe"
            item["capture_hook"]["transcript_path"] = parent_path
            item["capture_hook"]["cwd"] = cwd
            item["start_hook"]["transcript_path"] = child_path
            item["start_hook"]["cwd"] = cwd
            item["parent_rollout"]["path"] = parent_path
            item["child_rollout"]["path"] = child_path
            for rollout_name in ("parent_rollout", "child_rollout"):
                rollout = item[rollout_name]
                line = json.loads(rollout["session_meta_line"])
                line["payload"]["cwd"] = cwd
                rollout["session_meta_line"] = json.dumps(line) + "\n"

        result = identity_probe.validate_bundle(bundle)

        self.assertTrue(result["matrix_complete"])
        self.assertEqual(result["path_flavors"], {"posix": 0, "windows": 8})
        self.assertFalse(result["p2_live_qualified"])

    def test_mixed_parent_child_transcript_path_flavors_fail(self):
        bundle = copy.deepcopy(self.bundle)
        item = bundle["observations"][0]
        posix_path = "/private/tmp/rollouts/parent.jsonl"
        item["capture_hook"]["transcript_path"] = posix_path
        item["parent_rollout"]["path"] = posix_path
        windows_path = r"C:\Codex\rollouts\child.jsonl"
        item["start_hook"]["transcript_path"] = windows_path
        item["child_rollout"]["path"] = windows_path

        self.assert_invalid(bundle, "path flavors do not match")

    def test_wrong_start_child_id_fails(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"][0]["start_hook"]["agent_id"] = uuid7(999)

        self.assert_invalid(bundle, "start agent_id does not match child SessionMeta")

    def test_non_uuid_runtime_identity_fails(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"][0]["start_hook"]["agent_id"] = "child-by-name"

        self.assert_invalid(bundle, "must be a UUIDv7")

    def test_child_source_parent_mismatch_fails(self):
        bundle = copy.deepcopy(self.bundle)
        line = json.loads(bundle["observations"][0]["child_rollout"]["session_meta_line"])
        line["payload"]["source"]["subagent"]["thread_spawn"]["parent_thread_id"] = uuid7(998)
        bundle["observations"][0]["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "child source disagrees")

    def test_requested_name_prefix_match_is_not_accepted(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"][0]["capture_hook"]["tool_input"]["task_name"] = "nested"

        self.assert_invalid(bundle, "spawn canonical path is not the exact AgentPath join")

    def test_spawn_return_and_sessionmeta_path_mismatch_fails(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"][0]["spawn_result"]["task_name"] += "_other"

        self.assert_invalid(bundle, "spawn canonical path is not the exact AgentPath join")

    def test_nested_depth_mismatch_fails(self):
        bundle = copy.deepcopy(self.bundle)
        nested = next(
            item for item in bundle["observations"] if item["case_kind"].startswith("nested")
        )
        line = json.loads(nested["child_rollout"]["session_meta_line"])
        line["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 3
        nested["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "child source disagrees")

    def test_nested_parent_source_mismatch_fails(self):
        bundle = copy.deepcopy(self.bundle)
        nested = next(
            item for item in bundle["observations"] if item["case_kind"].startswith("nested")
        )
        line = json.loads(nested["parent_rollout"]["session_meta_line"])
        line["payload"]["source"]["subagent"]["thread_spawn"]["parent_thread_id"] = uuid7(997)
        nested["parent_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "parent source disagrees")

    def test_sessionmeta_cli_version_drift_fails(self):
        bundle = copy.deepcopy(self.bundle)
        item = bundle["observations"][0]
        line = json.loads(item["child_rollout"]["session_meta_line"])
        line["payload"]["cli_version"] = "0.148.0-alpha.10"
        item["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "cli_version is not pinned")

    def test_previous_runtime_pairs_remain_replayable(self):
        for runtime_role in (
            "migration_handoff_runtime",
            "schema_replay_runtime",
            "prior_signed_runtime",
        ):
            with self.subTest(runtime_role=runtime_role):
                previous_version = identity_probe.runtime_identity(
                    identity_probe.RUNTIME_EVIDENCE_INDEX, runtime_role
                )["codex_version"]
                bundle = copy.deepcopy(self.bundle)
                bundle["codex_version"] = previous_version
                bundle["source_commit"] = identity_probe.SUPPORTED_RUNTIME_PAIRS[
                    previous_version
                ]
                for observation_value in bundle["observations"]:
                    for rollout_name in ("parent_rollout", "child_rollout"):
                        rollout = observation_value[rollout_name]
                        line = json.loads(rollout["session_meta_line"])
                        line["payload"]["cli_version"] = previous_version
                        rollout["session_meta_line"] = json.dumps(line) + "\n"

                result = identity_probe.validate_bundle(bundle)

                self.assertTrue(result["mechanically_exact"])
                self.assertTrue(result["matrix_complete"])

    def test_runtime_version_cannot_pair_with_another_source_commit(self):
        bundle = copy.deepcopy(self.bundle)
        migration = identity_probe.runtime_identity(
            identity_probe.RUNTIME_EVIDENCE_INDEX, "migration_handoff_runtime"
        )
        bundle["source_commit"] = migration["source_commit"]

        self.assert_invalid(bundle, "unpinned runtime/source pair")

    def test_sessionmeta_payload_timestamp_after_record_fails(self):
        bundle = copy.deepcopy(self.bundle)
        item = bundle["observations"][0]
        line = json.loads(item["child_rollout"]["session_meta_line"])
        line["payload"]["timestamp"] = "2026-08-16T00:00:00.071Z"
        item["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "payload timestamp is later")

    def test_spawn_nickname_mismatch_fails(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"][0]["spawn_result"]["nickname"] = "wrong-nickname"

        self.assert_invalid(bundle, "spawn nickname disagrees")

    def test_duplicate_child_identity_fails(self):
        bundle = copy.deepcopy(self.bundle)
        first, second = bundle["observations"][:2]
        line = json.loads(second["child_rollout"]["session_meta_line"])
        duplicate = first["start_hook"]["agent_id"]
        second["start_hook"]["agent_id"] = duplicate
        line["payload"]["id"] = duplicate
        second["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "duplicate child_thread_id")

    def test_duplicate_spawn_tool_use_id_fails(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"][1]["capture_hook"]["tool_use_id"] = bundle["observations"][0][
            "capture_hook"
        ]["tool_use_id"]

        self.assert_invalid(bundle, "duplicate spawn_tool_use_id")

    def test_two_sessionmeta_lines_fail(self):
        bundle = copy.deepcopy(self.bundle)
        line = bundle["observations"][0]["child_rollout"]["session_meta_line"]
        bundle["observations"][0]["child_rollout"]["session_meta_line"] = line + line

        self.assert_invalid(bundle, "exactly one first SessionMeta line")

    def test_nonzero_first_sessionmeta_ordinal_fails(self):
        bundle = copy.deepcopy(self.bundle)
        item = bundle["observations"][0]
        line = json.loads(item["child_rollout"]["session_meta_line"])
        line["ordinal"] = 1
        item["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "first SessionMeta ordinal is not zero")

    def test_mixed_roles_fail_repeated_role_matrix(self):
        bundle = copy.deepcopy(self.bundle)
        item = bundle["observations"][0]
        item["capture_hook"]["tool_input"]["agent_type"] = "worker"
        item["start_hook"]["agent_type"] = "worker"
        line = json.loads(item["child_rollout"]["session_meta_line"])
        line["payload"]["agent_role"] = "worker"
        line["payload"]["source"]["subagent"]["thread_spawn"]["agent_role"] = "worker"
        item["child_rollout"]["session_meta_line"] = json.dumps(line) + "\n"

        self.assert_invalid(bundle, "more than one agent type")

    def test_cli_emits_non_authorizing_complete_fixture_receipt(self):
        path = self.root / "complete-bundle.json"
        path.write_text(json.dumps(self.bundle), encoding="utf-8")

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--bundle",
                str(path),
                "--require-complete-matrix",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["mechanically_exact"])
        self.assertTrue(result["matrix_complete"])
        self.assertEqual(result["adjudication_authority"], "none")
        self.assertFalse(result["p2_live_qualified"])

    def test_cli_requires_complete_matrix_without_promoting_live_qualification(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["observations"] = bundle["observations"][:1]
        path = self.root / "bundle.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--bundle",
                str(path),
                "--require-complete-matrix",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["valid"])
        self.assertFalse(result["matrix_complete"])
        self.assertFalse(result["p2_live_qualified"])


if __name__ == "__main__":
    unittest.main()
