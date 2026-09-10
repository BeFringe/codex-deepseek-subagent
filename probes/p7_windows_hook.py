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
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--guard', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
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
        result = subprocess.run(
            [sys.executable, str(args.guard), '--state-directory', str(args.state),
             '--plaintext-agent-type', 'g4_qualification_probe_worker'],
            input=raw, capture_output=True, timeout=20,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
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
