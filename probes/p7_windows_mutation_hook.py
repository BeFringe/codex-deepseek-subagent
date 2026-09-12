"""Capture the exact isolated native Hook invocation, then run the G4 guard.

Raw assignment material stays in the private probe directory, never in a commit.
No credential file or environment value is inspected by this observer.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import stat
import uuid


def publish_marker(path, value):
    temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    if path.exists():
        raise ValueError('duplicate schedule marker')
    os.replace(temporary, path)


def wait_marker(path):
    deadline = time.monotonic() + 120
    while not path.exists():
        if time.monotonic() >= deadline:
            raise ValueError('qualification schedule barrier timed out')
        time.sleep(0.025)
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--guard', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--write-target')
    parser.add_argument('--dirty-foreign-after-start', type=Path)
    parser.add_argument('--parent-claim-barrier', action='store_true')
    args = parser.parse_args()
    started = time.time_ns()
    raw = sys.stdin.buffer.read()
    record = {
        'schema': 1, 'started_ns': started,
        'stdin_sha256': hashlib.sha256(raw).hexdigest(), 'stdin_bytes': len(raw),
    }
    stdout, stderr, code = b'', b'', 2
    try:
        record['stdin_utf8'] = raw.decode('utf-8')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Hook input is not an object')
        record['input'] = payload
        schedule_actor = None
        if args.parent_claim_barrier and payload.get('hook_event_name') == 'PreToolUse' and payload.get('tool_name') == 'apply_patch':
            from writer_lease_guard import actor_identity_from_hook
            schedule_actor = actor_identity_from_hook(payload)
            if schedule_actor['canonical_agent_path'] == '/root':
                ready = wait_marker(args.events / 'schedule-ready.marker')
                record['schedule_ready_observed'] = {'time_ns': time.time_ns(), 'marker': ready}
        guard_args = [sys.executable, str(args.guard), '--state-directory', str(args.state),
                      '--plaintext-agent-type', 'g4_qualification_probe_worker']
        if args.write_target:
            guard_args += ['--child-write-probe', args.write_target]
        result = subprocess.run(
            guard_args,
            input=raw, capture_output=True, timeout=20,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        if schedule_actor is not None:
            from compatibility_state import StateStore
            store = StateStore(args.state)
            decision = json.loads(stdout).get('hookSpecificOutput', {})
            if code != 0:
                raise ValueError('guard failed at schedule boundary')
            if schedule_actor['canonical_agent_path'] == '/root':
                if decision.get('permissionDecision') != 'deny':
                    raise ValueError('parent overlapping request was not denied')
                conflicts = [p for p in (args.state / 'writer_conflict').glob('*.json')
                             if json.loads(p.read_text())['tool_use_id'] == payload['tool_use_id']]
                if len(conflicts) != 1:
                    raise ValueError('exact durable parent conflict absent')
                conflict = json.loads(conflicts[0].read_text())
                if not any(item.get('claim_id') == ready['claim_id'] for item in conflict['conflicts']):
                    raise ValueError('parent conflict did not bind held child claim')
                marker = {'time_ns': time.time_ns(), 'claim_id': ready['claim_id'],
                          'tool_use_id': payload['tool_use_id'], 'conflict': conflict,
                          'conflict_sha256': hashlib.sha256(conflicts[0].read_bytes()).hexdigest()}
                publish_marker(args.events / 'schedule-release.marker', marker)
                record['schedule_release_published'] = marker
            else:
                claims = [store.read_writer_claim(p.stem) for p in (args.state / 'writer_claim').glob('*.json')]
                claims = [c for c in claims if c['actor'] == schedule_actor and c['tool_use_id'] == payload['tool_use_id']]
                if len(claims) != 1 or decision.get('permissionDecision') == 'deny':
                    raise ValueError('exact native child claim absent')
                claim = claims[0]
                if claim['paths'] != ['qualified.txt']:
                    raise ValueError('schedule claim outside exact ceiling')
                marker = {'time_ns': time.time_ns(), 'claim_id': claim['claim_id'],
                          'claim_sha256': claim['claim_sha256'], 'actor': schedule_actor,
                          'tool_use_id': payload['tool_use_id']}
                publish_marker(args.events / 'schedule-ready.marker', marker)
                record['schedule_ready_published'] = marker
                release = wait_marker(args.events / 'schedule-release.marker')
                if release['claim_id'] != claim['claim_id'] or store.read_writer_claim(claim['claim_id']) != claim:
                    raise ValueError('held child claim drift')
                record['schedule_release_observed'] = {'time_ns': time.time_ns(), 'marker': release}
        if args.dirty_foreign_after_start and payload.get('hook_event_name') == 'SubagentStart':
            target = args.dirty_foreign_after_start
            output = json.loads(stdout) if stdout.strip() else {}
            context = output.get('hookSpecificOutput', {}).get('additionalContext', '')
            root = Path(payload['cwd']).resolve(strict=True)
            if (code != 0 or 'BEGIN CODEX WORKER CAPSULE' not in context
                    or payload.get('agent_type') != 'g4_qualification_probe_worker'
                    or root.parent != Path(tempfile.gettempdir()).resolve()
                    or not root.name.startswith('codex-g4-write-windows-')
                    or target != root / 'foreign.txt' or target.resolve(strict=True) != target
                    or target.stat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('negative fixture boundary rejected')
            before = target.read_bytes()
            if before != b'FOREIGN_TRACKED_BASELINE\n':
                raise ValueError('negative fixture was already modified')
            after = b'FOREIGN_DIRTY_BYTES_MUST_SURVIVE\n'
            target.write_bytes(after)
            record['negative_fixture_setup'] = {
                'source': 'isolated_test_fixture_after_child_binding_before_model_start',
                'path': str(target), 'before_sha256': hashlib.sha256(before).hexdigest(),
                'after_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'test_only_injection': True,
            }
        record['stdout'] = stdout.decode('utf-8')
        record['stderr'] = stderr.decode('utf-8')
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        # Retain failed observations too; never emit an incomplete allow result.
        record['observer_error'] = type(error).__name__
        stdout, stderr, code = b'', b'P7 Hook observer failed closed\n', 2
    record['exit_code'] = code
    record['finished_ns'] = time.time_ns()
    # One exclusive file per event avoids concurrent JSONL append corruption.
    target = args.events / (str(started) + '-' + uuid.uuid4().hex + '.json')
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, ensure_ascii=False, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    sys.stdout.buffer.write(stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
