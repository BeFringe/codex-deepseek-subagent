import datetime
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from private_output_assertions import assert_private_output


def resolve_script():
    override = os.environ.get("PLAINTEXT_HANDOFF_SCRIPT")
    if override:
        script = Path(override).expanduser().resolve()
        if script.is_file():
            return script
        raise FileNotFoundError(
            f"PLAINTEXT_HANDOFF_SCRIPT does not name a file: {script}"
        )

    test_directory = Path(__file__).resolve().parent
    candidates = (
        test_directory.parent / "hooks" / "plaintext_handoff.py",
        test_directory.parent / "plaintext_handoff.py",
    )
    for script in candidates:
        if script.is_file():
            return script
    attempted = ", ".join(str(script) for script in candidates)
    raise FileNotFoundError(
        "Could not locate plaintext_handoff.py in a supported test layout; "
        f"checked: {attempted}. Set PLAINTEXT_HANDOFF_SCRIPT explicitly."
    )


SCRIPT = resolve_script()
AGENT_TYPE = "v4_flash_worker"
HANDOFF_COMMAND = (["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-File", str(SCRIPT.with_name("plaintext-handoff.ps1"))]
                   if os.name == "nt" else [sys.executable, str(SCRIPT)])
MODE_ARGUMENT = "-Mode" if os.name == "nt" else "--mode"
STATE_ARGUMENT = "-StateDirectory" if os.name == "nt" else "--state-directory"


def utc_timestamp(*, seconds_from_now=0):
    return (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=seconds_from_now)
    ).isoformat()


def envelope(assignment="read the logs", *, expires_in=300, **overrides):
    value = {
        "schema": 1,
        "handoff_id": "00000000-0000-0000-0000-000000000001",
        "agent_type": AGENT_TYPE,
        "created_at": utc_timestamp(),
        "expires_at": utc_timestamp(seconds_from_now=expires_in),
        "assignment": assignment,
    }
    value.update(overrides)
    return value


class PlaintextHandoffCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_directory = Path(self.temporary_directory.name) / "state"

    def tearDown(self):
        self.temporary_directory.cleanup()

    @property
    def pending_path(self):
        return self.state_directory / f"{AGENT_TYPE}.pending.json"

    def invoke(self, mode, stdin, *extra_arguments):
        return self.invoke_at(self.state_directory, mode, stdin, *extra_arguments)

    def invoke_at(self, state_directory, mode, stdin, *extra_arguments):
        if os.name == "nt":
            extra_arguments = tuple("-TtlSeconds" if value == "--ttl-seconds" else value
                                    for value in extra_arguments)
        result = subprocess.run(
            [
                *HANDOFF_COMMAND,
                MODE_ARGUMENT,
                mode,
                STATE_ARGUMENT,
                str(state_directory),
                *extra_arguments,
            ],
            input=stdin.encode('utf-8'),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return subprocess.CompletedProcess(result.args, result.returncode,
                                           result.stdout.decode('utf-8'), result.stderr.decode('utf-8'))

    def write_pending(self, value):
        self.state_directory.mkdir(parents=True, exist_ok=True)
        self.pending_path.write_text(json.dumps(value), encoding="utf-8")

    def target_hook_input(self, agent_id="agent-1"):
        return json.dumps(
            {
                "hook_event_name": "SubagentStart",
                "agent_type": AGENT_TYPE,
                "agent_id": agent_id,
            }
        )

    def handoff_state_files(self):
        return sorted(self.state_directory.glob(f"{AGENT_TYPE}.*.json"))

    # Baseline contract: these tests capture the behavior relied upon by the skill.

    def test_stage_creates_private_pending_envelope_without_echoing_assignment(self):
        assignment = "Inspect only the bounded fixture.\n"

        result = self.invoke("stage", assignment, "--ttl-seconds", "60")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        staged = json.loads(self.pending_path.read_text(encoding="utf-8"))
        self.assertTrue(output["staged"])
        self.assertEqual(output["agent_type"], AGENT_TYPE)
        self.assertEqual(staged["schema"], 1)
        self.assertEqual(staged["assignment"], assignment)
        self.assertNotIn(assignment.strip(), result.stdout)
        assert_private_output(self, self.pending_path)

    def test_hook_consumes_one_valid_assignment_and_emits_additional_context(self):
        assignment = "Summarize the supplied build log."
        self.write_pending(envelope(assignment))

        result = self.invoke("hook", self.target_hook_input())

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SubagentStart")
        self.assertIn("BEGIN PARENT ASSIGNMENT\n" + assignment, output["additionalContext"])
        self.assertFalse(self.handoff_state_files())

    def test_hook_ignores_non_target_agents_without_consuming_pending(self):
        original = envelope()
        self.write_pending(original)
        hook_input = json.dumps(
            {
                "hook_event_name": "SubagentStart",
                "agent_type": "default",
                "agent_id": "agent-1",
            }
        )

        result = self.invoke("hook", hook_input)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(self.pending_path.read_text()), original)

    def test_hook_ignores_non_target_events_without_consuming_pending(self):
        original = envelope("leave this assignment untouched")
        self.write_pending(original)
        hook_input = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "agent_type": AGENT_TYPE,
                "agent_id": "agent-1",
            }
        )

        result = self.invoke("hook", hook_input)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(self.pending_path.read_text()), original)

    def test_stage_refuses_to_replace_an_active_pending_assignment(self):
        original = envelope("first assignment")
        self.write_pending(original)

        result = self.invoke("stage", "second assignment")

        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(self.pending_path.read_text()), original)

    def test_stage_refuses_while_an_unexpired_claim_exists(self):
        self.state_directory.mkdir(parents=True)
        claimed = self.state_directory / f"{AGENT_TYPE}.claimed.running-agent.json"
        active = envelope("assignment already owned by a running child")
        claimed.write_text(json.dumps(active), encoding="utf-8")

        result = self.invoke("stage", "new assignment")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(json.loads(claimed.read_text()), active)
        self.assertFalse(self.pending_path.exists())

    def test_stage_quarantines_expired_claim_with_blank_assignment(self):
        # A structurally invalid claim must never be TTL-cleaned. Preserve it
        # under a quarantine name and keep blocking until explicit resolution.
        self.state_directory.mkdir(parents=True)
        claimed = self.state_directory / f"{AGENT_TYPE}.claimed.stale-agent.json"
        invalid = envelope("   \n", expires_in=-10)
        claimed.write_text(json.dumps(invalid), encoding="utf-8")

        result = self.invoke("stage", "replacement assignment")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(claimed.exists())
        quarantined = list(self.state_directory.glob(f"{AGENT_TYPE}.failed.*.json"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(json.loads(quarantined[0].read_text()), invalid)
        self.assertFalse(self.pending_path.exists())

    # Robustness contract: unknown state is preserved; known-expired state is cleaned.

    def test_stage_replaces_a_structurally_valid_expired_pending_assignment(self):
        self.write_pending(envelope("expired assignment", expires_in=-10))

        result = self.invoke("stage", "fresh assignment")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.pending_path.read_text())["assignment"], "fresh assignment")
        assert_private_output(self, self.pending_path)

    def test_stage_never_replaces_structurally_invalid_expired_envelopes(self):
        invalid_cases = {
            "missing_handoff_id": ({}, "handoff_id"),
            "invalid_handoff_id": ({"handoff_id": "not-a-uuid"}, None),
            "missing_created_at": ({}, "created_at"),
            "invalid_created_at": ({"created_at": "yesterday-ish"}, None),
            "non_string_assignment": ({"assignment": ["not", "plaintext"]}, None),
            "empty_assignment": ({"assignment": ""}, None),
            "whitespace_assignment": ({"assignment": "  \n"}, None),
        }
        for case_name, (overrides, missing_field) in invalid_cases.items():
            with self.subTest(case=case_name):
                state_directory = self.state_directory / case_name
                state_directory.mkdir(parents=True)
                pending = state_directory / f"{AGENT_TYPE}.pending.json"
                invalid = envelope("expired but invalid", expires_in=-10)
                invalid.update(overrides)
                if missing_field is not None:
                    invalid.pop(missing_field)
                pending.write_text(json.dumps(invalid), encoding="utf-8")

                result = self.invoke_at(state_directory, "stage", "replacement assignment")

                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(json.loads(pending.read_text()), invalid)

    def test_stage_rejects_timezone_naive_timestamps_without_losing_state(self):
        invalid_cases = {
            "created_at": {"created_at": "2026-08-08T12:00:00"},
            "expires_at": {"expires_at": "2026-08-08T12:05:00"},
        }
        for case_name, overrides in invalid_cases.items():
            with self.subTest(field=case_name):
                state_directory = self.state_directory / case_name
                state_directory.mkdir(parents=True)
                pending = state_directory / f"{AGENT_TYPE}.pending.json"
                invalid = envelope("must survive", **overrides)
                pending.write_text(json.dumps(invalid), encoding="utf-8")

                result = self.invoke_at(state_directory, "stage", "replacement assignment")

                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(json.loads(pending.read_text()), invalid)

    def test_stage_rejects_corrupt_pending_json_without_traceback_or_data_loss(self):
        corrupt = b'{"schema":1,"assignment":"unfinished'
        self.state_directory.mkdir(parents=True)
        self.pending_path.write_bytes(corrupt)

        result = self.invoke("stage", "replacement assignment")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.pending_path.read_bytes(), corrupt)

    def test_stage_rejects_malformed_expiry_without_traceback_or_replacement(self):
        original = envelope(expires_at="definitely-not-a-timestamp")
        self.write_pending(original)

        result = self.invoke("stage", "replacement assignment")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(json.loads(self.pending_path.read_text()), original)

    def test_hook_rejects_malformed_json_input_without_traceback(self):
        result = self.invoke("hook", "not-json")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("invalid JSON", result.stderr)

    def test_hook_rejects_non_object_json_input_without_traceback(self):
        result = self.invoke("hook", "[]")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_hook_preserves_assignment_when_envelope_validation_fails(self):
        invalid = envelope("must not be lost", schema=999)
        self.write_pending(invalid)

        result = self.invoke("hook", self.target_hook_input())

        self.assertNotEqual(result.returncode, 0)
        remaining = self.handoff_state_files()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(json.loads(remaining[0].read_text()), invalid)

    def test_hook_preserves_corrupt_pending_bytes_on_validation_failure(self):
        corrupt = b'{"schema":1,"assignment":"must survive'
        self.state_directory.mkdir(parents=True)
        self.pending_path.write_bytes(corrupt)

        result = self.invoke("hook", self.target_hook_input())

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        remaining = self.handoff_state_files()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].read_bytes(), corrupt)

    def test_hook_preserves_assignment_with_malformed_expiry(self):
        invalid = envelope("must not be lost", expires_at="invalid")
        self.write_pending(invalid)

        result = self.invoke("hook", self.target_hook_input())

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        remaining = self.handoff_state_files()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(json.loads(remaining[0].read_text()), invalid)

    def test_hook_reports_missing_assignment_as_transport_failure(self):
        result = self.invoke("hook", self.target_hook_input())

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("handoff", result.stderr.lower())

    def test_two_concurrent_target_hooks_deliver_at_most_once(self):
        assignment = "deliver at most once"
        self.write_pending(envelope(assignment))
        start_gate = threading.Barrier(3)

        def invoke_after_gate(agent_id):
            start_gate.wait()
            return self.invoke("hook", self.target_hook_input(agent_id))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(invoke_after_gate, "agent-one"),
                executor.submit(invoke_after_gate, "agent-two"),
            ]
            start_gate.wait()
            results = [future.result(timeout=10) for future in futures]

        successes = [result for result in results if result.returncode == 0]
        failures = [result for result in results if result.returncode != 0]
        self.assertEqual(len(successes), 1, [(r.returncode, r.stderr) for r in results])
        self.assertEqual(len(failures), 1, [(r.returncode, r.stderr) for r in results])
        self.assertIn(assignment, successes[0].stdout)
        self.assertIn("handoff", failures[0].stderr.lower())
        self.assertFalse(self.handoff_state_files())

    def test_reviewer_role_child_racing_target_child_never_consumes_pending(self):
        # A child with a different role (for example a reviewer subagent) must
        # never consume a v4_flash_worker assignment, even when it starts at the
        # same moment as the intended worker.
        assignment = "only for the v4_flash_worker"
        self.write_pending(envelope(assignment))
        start_gate = threading.Barrier(3)

        def invoke_after_gate(agent_type, agent_id):
            start_gate.wait()
            hook_input = json.dumps(
                {
                    "hook_event_name": "SubagentStart",
                    "agent_type": agent_type,
                    "agent_id": agent_id,
                }
            )
            return self.invoke("hook", hook_input)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(invoke_after_gate, "reviewer", "reviewer-1"),
                executor.submit(invoke_after_gate, AGENT_TYPE, "worker-1"),
            ]
            start_gate.wait()
            reviewer_result, worker_result = [future.result(timeout=30) for future in futures]

        self.assertEqual(reviewer_result.returncode, 0, reviewer_result.stderr)
        self.assertEqual(reviewer_result.stdout, "")
        self.assertEqual(worker_result.returncode, 0, worker_result.stderr)
        delivered = json.loads(worker_result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(assignment, delivered)
        self.assertFalse(self.handoff_state_files())

    def test_concurrent_target_hooks_never_deliver_an_expired_pending(self):
        # Two children racing for an already-expired pending assignment must
        # both fail closed: the winner consumes and reports the expiry, the
        # loser sees the handoff is gone or the lock is held, and the expired
        # assignment is never delivered to either child.
        self.write_pending(envelope("expired secret", expires_in=-10))
        start_gate = threading.Barrier(3)

        def invoke_after_gate(agent_id):
            start_gate.wait()
            return self.invoke("hook", self.target_hook_input(agent_id))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(invoke_after_gate, "agent-one"),
                executor.submit(invoke_after_gate, "agent-two"),
            ]
            start_gate.wait()
            results = [future.result(timeout=30) for future in futures]

        for result in results:
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("BEGIN PARENT ASSIGNMENT", result.stdout)
            self.assertNotIn("expired secret", result.stdout)
        self.assertEqual([r.returncode for r in results].count(6), 1)
        self.assertNotIn(0, [r.returncode for r in results])
        self.assertFalse(self.handoff_state_files())

    def test_stage_racing_hook_over_expired_pending_never_delivers_expired_assignment(self):
        # A stage recovering an expired pending can race the Hook claim of the
        # next child. Whichever acquires the dispatch lock first, the expired
        # assignment must never be delivered, and a complete fresh envelope must
        # eventually be published or delivered.
        self.write_pending(envelope("EXPIRED-SECRET-ASSIGNMENT", expires_in=-10))
        start_gate = threading.Barrier(3)

        def stage_after_gate():
            start_gate.wait()
            return self.invoke("stage", "FRESH-ASSIGNMENT")

        def hook_after_gate():
            start_gate.wait()
            return self.invoke("hook", self.target_hook_input("racing-child"))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(stage_after_gate), executor.submit(hook_after_gate)]
            start_gate.wait()
            stage_result, hook_result = [future.result(timeout=30) for future in futures]

        self.assertNotIn("Traceback", stage_result.stderr)
        self.assertNotIn("Traceback", hook_result.stderr)
        self.assertNotIn("EXPIRED-SECRET-ASSIGNMENT", hook_result.stdout)
        if "BEGIN PARENT ASSIGNMENT" in hook_result.stdout:
            self.assertIn("FRESH-ASSIGNMENT", hook_result.stdout)
            self.assertFalse(self.handoff_state_files())
        else:
            self.assertTrue(self.retry_stage_publishes_fresh_envelope())

    def test_stage_racing_hook_over_expired_claim_recovers_it_fail_closed(self):
        # Recovery of an expired orphan claim races a fresh stage and the next
        # Hook claim. The orphan must be removed by the recovery, its content
        # must never be delivered, and a fresh envelope must eventually exist.
        self.state_directory.mkdir(parents=True)
        orphan = self.state_directory / f"{AGENT_TYPE}.claimed.crashed-agent.json"
        orphan.write_text(json.dumps(envelope("ORPHAN-SECRET-ASSIGNMENT", expires_in=-10)), encoding="utf-8")
        start_gate = threading.Barrier(3)

        def stage_after_gate():
            start_gate.wait()
            return self.invoke("stage", "FRESH-ASSIGNMENT")

        def hook_after_gate():
            start_gate.wait()
            return self.invoke("hook", self.target_hook_input("racing-child"))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(stage_after_gate), executor.submit(hook_after_gate)]
            start_gate.wait()
            stage_result, hook_result = [future.result(timeout=30) for future in futures]

        self.assertNotIn("Traceback", stage_result.stderr)
        self.assertNotIn("Traceback", hook_result.stderr)
        self.assertNotIn("ORPHAN-SECRET-ASSIGNMENT", hook_result.stdout)
        self.assertFalse(orphan.exists())
        if "BEGIN PARENT ASSIGNMENT" in hook_result.stdout:
            self.assertIn("FRESH-ASSIGNMENT", hook_result.stdout)
            self.assertFalse(self.handoff_state_files())
        else:
            self.assertTrue(self.retry_stage_publishes_fresh_envelope())

    def retry_stage_publishes_fresh_envelope(self):
        # The parent protocol retries a stage until the occupied state is
        # explicitly clear; lock contention and an in-flight claim are expected
        # transient outcomes of the race, never a reason to deliver stale bytes.
        for attempt in range(5):
            if self.pending_path.exists():
                try:
                    pending = json.loads(self.pending_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    pending = None
                if pending is not None and pending.get("assignment", "").startswith("FRESH"):
                    return True
            result = self.invoke("stage", "FRESH-ASSIGNMENT")
            if result.returncode == 0:
                self.assertNotIn("Traceback", result.stderr)
                return True
        return False

    def test_concurrent_stages_publish_exactly_one_complete_envelope(self):
        # Launch several stages concurrently and release their communicate()
        # through a single barrier, so input and EOF reach all children at the
        # same moment and they genuinely contend for the dispatch lock. The lock
        # must admit exactly one winner, and the published pending envelope must
        # be that winner's, complete.
        self.write_pending(envelope("old expired assignment", expires_in=-60))
        command = [
            *HANDOFF_COMMAND,
                MODE_ARGUMENT,
            "stage",
            STATE_ARGUMENT,
            str(self.state_directory),
        ]
        start_barrier = threading.Barrier(7)  # six stage runners + the test
        results = [None] * 6

        def run_stage(job):
            start_barrier.wait()
            completed = subprocess.run(
                command,
                input=f"job-{job}",
                capture_output=True,
                text=True,
                timeout=30,
            )
            results[job] = (completed.returncode, completed.stdout, completed.stderr)

        runners = [
            threading.Thread(target=run_stage, args=(job,), daemon=True)
            for job in range(6)
        ]
        for runner in runners:
            runner.start()
        start_barrier.wait()
        for runner in runners:
            runner.join()

        for returncode, _, stderr in results:
            self.assertNotIn("Traceback", stderr)
        successes = [result for result in results if result[0] == 0]
        self.assertEqual(len(successes), 1, [(r[0], r[2]) for r in results])

        pending = json.loads(self.pending_path.read_text(encoding="utf-8"))
        winner = json.loads(successes[0][1])
        self.assertTrue(pending["assignment"].startswith("job-"))
        self.assertEqual(winner["handoff_id"], pending["handoff_id"])

        delivered = self.invoke("hook", self.target_hook_input("winner-consumer"))
        self.assertEqual(delivered.returncode, 0, delivered.stderr)
        delivered_context = json.loads(delivered.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(pending["assignment"], delivered_context)
        self.assertFalse(self.handoff_state_files())

    def test_stage_fails_while_dispatch_lock_is_held(self):
        # Hold the dispatch lock from the test process, then stage: the
        # nonblocking acquire must fail deterministically without touching state.
        self.state_directory.mkdir(parents=True)
        lock_path = self.state_directory / f".{AGENT_TYPE}.lock"
        if os.name == "nt":
            # Match the PowerShell backend's FileShare.None dispatch lease.
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                          wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.CreateFileW(str(lock_path), 0xC0000000, 0, None, 4, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
            try:
                result = self.invoke("stage", "blocked by a held dispatch lock")
            finally:
                kernel.CloseHandle(handle)
            self.assertEqual(result.returncode, 13, result.stderr)
            self.assertIn("already in progress", result.stderr)
            self.assertFalse(self.pending_path.exists())
            return
        import fcntl
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            result = self.invoke("stage", "blocked by a held dispatch lock")
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

        self.assertEqual(result.returncode, 13)
        self.assertIn("already in progress", result.stderr)
        self.assertFalse(self.pending_path.exists())

    def test_stage_cannot_publish_while_hook_delivery_is_still_active(self):
        assignment = "active hook assignment\n" + ("x" * (1024 * 1024))
        active = envelope(assignment, expires_in=2)
        self.write_pending(active)
        command = [
            *HANDOFF_COMMAND,
                MODE_ARGUMENT,
            "hook",
            STATE_ARGUMENT,
            str(self.state_directory),
        ]
        hook = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        hook.stdin.write(self.target_hook_input("slow-output-agent"))
        hook.stdin.close()

        deadline = time.monotonic() + 10
        claimed = []
        while time.monotonic() < deadline:
            claimed = list(self.state_directory.glob(f"{AGENT_TYPE}.claimed.*.json"))
            if claimed:
                break
            if hook.poll() is not None:
                self.fail("hook completed before its active claim could be observed")
            time.sleep(0.001)
        self.assertEqual(len(claimed), 1)
        self.assertFalse(self.pending_path.exists())
        self.assertIsNone(hook.poll(), "the claim must be observed while delivery is still blocked on undrained output")

        expires_at = datetime.datetime.fromisoformat(active["expires_at"])
        while datetime.datetime.now(datetime.timezone.utc) <= expires_at:
            time.sleep(0.01)
        competing = self.invoke("stage", "must not enter the occupied slot")

        hook_stdout = hook.stdout.read()
        hook_stderr = hook.stderr.read()
        hook_returncode = hook.wait(timeout=15)
        hook.stdout.close()
        hook.stderr.close()

        self.assertNotEqual(competing.returncode, 0)
        self.assertFalse(self.pending_path.exists())
        self.assertEqual(hook_returncode, 0, hook_stderr)
        delivered_context = json.loads(hook_stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(assignment, delivered_context)
        self.assertFalse(self.handoff_state_files())

    def test_hook_does_not_overwrite_an_existing_conflicting_claim(self):
        pending = envelope("new pending assignment")
        existing_claim = envelope("assignment already claimed by this agent")
        self.write_pending(pending)
        claimed = self.state_directory / f"{AGENT_TYPE}.claimed.same-agent.json"
        claimed.write_text(json.dumps(existing_claim), encoding="utf-8")

        result = self.invoke("hook", self.target_hook_input("same-agent"))

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(json.loads(self.pending_path.read_text()), pending)
        self.assertEqual(json.loads(claimed.read_text()), existing_claim)

    def test_hook_rejects_timezone_naive_timestamps_without_losing_state(self):
        invalid_cases = {
            "created_at": {"created_at": "2026-08-08T12:00:00"},
            "expires_at": {"expires_at": "2026-08-08T12:05:00"},
        }
        for case_name, overrides in invalid_cases.items():
            with self.subTest(field=case_name):
                state_directory = self.state_directory / case_name
                state_directory.mkdir(parents=True)
                pending = state_directory / f"{AGENT_TYPE}.pending.json"
                invalid = envelope("must survive", **overrides)
                pending.write_text(json.dumps(invalid), encoding="utf-8")

                result = self.invoke_at(
                    state_directory,
                    "hook",
                    self.target_hook_input(f"agent-{case_name}"),
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                remaining = sorted(state_directory.glob(f"{AGENT_TYPE}.*.json"))
                self.assertEqual(len(remaining), 1)
                self.assertEqual(json.loads(remaining[0].read_text()), invalid)

    def test_hook_removes_a_known_expired_pending_assignment(self):
        self.write_pending(envelope("expired assignment", expires_in=-10))

        result = self.invoke("hook", self.target_hook_input())

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.handoff_state_files())

    def test_hook_cleans_expired_claim_when_no_live_holder_exists(self):
        self.state_directory.mkdir(parents=True)
        orphan = self.state_directory / f"{AGENT_TYPE}.claimed.crashed-agent.json"
        # The fixture is created directly and no Hook subprocess exists, so the
        # absence of an active holder is known independently of the expired TTL.
        orphan.write_text(json.dumps(envelope(expires_in=-10)), encoding="utf-8")

        result = self.invoke("hook", self.target_hook_input("new-agent"))

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(orphan.exists())

    def test_stage_never_exposes_a_partially_written_pending_envelope(self):
        # A large assignment widens the publication window enough for this test to
        # observe direct-to-final-path writes. Atomic implementations publish only
        # after the complete JSON document has been written and synced.
        assignment = "x" * (16 * 1024 * 1024)
        command = [
            *HANDOFF_COMMAND,
                MODE_ARGUMENT,
            "stage",
            STATE_ARGUMENT,
            str(self.state_directory),
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.stdin.write(assignment)
        process.stdin.close()
        malformed_observation = None
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            if self.pending_path.exists():
                try:
                    json.loads(self.pending_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
                    malformed_observation = error
                    break
            time.sleep(0.001)
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        returncode = process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()

        self.assertEqual(returncode, 0, stderr)
        self.assertIsNone(malformed_observation, "a partial pending JSON document was observable")
        self.assertEqual(json.loads(stdout)["agent_type"], AGENT_TYPE)


if __name__ == "__main__":
    unittest.main()
