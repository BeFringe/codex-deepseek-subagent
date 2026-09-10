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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--guard', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--write-target')
    parser.add_argument('--dirty-foreign-after-start', type=Path)
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
        guard_args = [sys.executable, str(args.guard), '--state-directory', str(args.state),
                      '--plaintext-agent-type', 'g4_qualification_probe_worker']
        if args.write_target:
            guard_args += ['--child-write-probe', args.write_target]
        result = subprocess.run(
            guard_args,
            input=raw, capture_output=True, timeout=20,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
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
