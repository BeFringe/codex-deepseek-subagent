"""Controlled schedules over real StateStore locks and publication, not native live proof.

The test fixture supplies synthetic identities only. Gate instrumentation calls
the unmodified implementation and never supplies a decision or state result.
Every fixture is retained, including failures. No probabilistic repetition.
"""
import argparse
import contextlib
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hooks'))
spec = importlib.util.spec_from_file_location('schedule_fixture', ROOT / 'tests/test_assignment_transport.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def states(store):
    return {p.relative_to(store.root).as_posix(): {'sha256': sha(p), 'value': json.loads(p.read_text())}
            for p in sorted(store.root.rglob('*.json'))}


class Gate:
    def __init__(self, store, bucket):
        self.events = []
        self.held = threading.Event()
        self.release = threading.Event()
        self.contender = threading.Event()
        self.owner = None
        original_publish, original_lock = store._publish, store.locked

        def publish(target, value, *, replace=False):
            original_publish(target, value, replace=replace)
            self.mark('published', path=str(target), sha256=sha(target), value=value)
            if target.parent.name == bucket and not self.held.is_set():
                self.owner = threading.get_ident()
                self.mark('gate_held', bucket=bucket)
                self.held.set()
                require(self.release.wait(30), 'controller did not release gate')

        @contextlib.contextmanager
        def locked():
            self.mark('lock_attempt')
            if self.held.is_set() and not self.release.is_set() and threading.get_ident() != self.owner:
                self.contender.set()
            with original_lock():
                self.mark('lock_acquired')
                yield
                self.mark('lock_releasing')
            self.mark('lock_released')

        store._publish, store.locked = publish, locked

    def mark(self, event, **data):
        self.events.append({'event': event, 'time_ns': time.time_ns(),
                            'pid': os.getpid(), 'thread_id': threading.get_ident(), **data})

    def pair(self, first, second):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(first)
            try:
                require(self.held.wait(30), 'owner did not reach publication gate')
                b = pool.submit(second)
                require(self.contender.wait(30), 'contender did not reach real lock')
                require(not b.done(), 'contender returned while owner held lock')
                self.mark('controller_release')
            finally:
                self.release.set()
            return a.result(timeout=30), b.result(timeout=30)


def make_fixture():
    f = fixture.AssignmentTransportTests()
    f.setUp()
    f.temporary_directory._finalizer.detach()
    return f


def spawn(f, task):
    authority = fixture.assignment_transport.parse_authority_declaration(f.message())
    authority['owned_paths'], authority['excluded_paths'] = ['owned/' + task], []
    return f.spawn_hook(task, tool_input={'message': f.message(authority=authority)})


def binding(bucket):
    f = make_fixture()
    hooks = [spawn(f, task) for task in ('one', 'two')]
    children = [f.child_hook(task) for task in ('one', 'two')]
    if bucket != 'pending':
        for hook in hooks:
            require('HANDOFF.STAGED' in f.capture(hook)['hookSpecificOutput']['additionalContext'], 'capture failed')
    gate = Gate(f.store, bucket)
    if bucket == 'pending':
        captured = gate.pair(lambda: f.capture(hooks[0]), lambda: f.capture(hooks[1]))
        require(all('HANDOFF.STAGED' in r['hookSpecificOutput']['additionalContext'] for r in captured), 'capture denied')
        results = [fixture.assignment_transport.subagent_start(f.store, hook) for hook in children]
    else:
        results = gate.pair(lambda: fixture.assignment_transport.subagent_start(f.store, children[0]),
                            lambda: fixture.assignment_transport.subagent_start(f.store, children[1]))
    mapping = []
    for task, hook, child, result in zip(('one', 'two'), hooks, children, results):
        context = result['hookSpecificOutput']['additionalContext']
        require('BEGIN CODEX WORKER CAPSULE' in context, 'binding failed: ' + context)
        capsule = json.loads(context.split('BEGIN CODEX WORKER CAPSULE\n')[1].split('\nEND CODEX WORKER CAPSULE')[0])
        envelope = f.store._validated_envelope(f.store.path('active', capsule['assignment_id']))
        require(capsule['requested_task_name'] == task and capsule['spawn_tool_use_id'] == hook['tool_use_id']
                and capsule['canonical_agent_path'] == '/root/' + task
                and envelope['binding']['child_thread_id'] == child['agent_id'], 'identity cross-binding')
        mapping.append({'capsule': capsule, 'binding': envelope['binding']})
    require(len({m['capsule']['assignment_id'] for m in mapping}) == 2, 'assignments aliased')
    require(not list((f.store.root / 'pending').glob('*.json'))
            and not list((f.store.root / 'claimed').glob('*.json')), 'unconsumed handoff remains')
    return {'schedule': bucket, 'root': str(f.root), 'events': gate.events,
            'mapping': mapping, 'state': states(f.store), 'result': 'exact_binding'}


def writer():
    f = make_fixture()
    first = f.parent_patch_hook(tool_use_id='held-parent-call')
    second = f.parent_patch_hook(tool_use_id='blocked-parent-call')
    gate = Gate(f.store, 'writer_claim')

    def contender():
        result = fixture.writer_lease_guard.pre_tool_use(f.store, second)
        # Capture the durable receipt at the actual return boundary.
        gate.mark('blocked_return', result=result, durable_state=states(f.store))
        return result

    allowed, denied = gate.pair(lambda: fixture.writer_lease_guard.pre_tool_use(f.store, first), contender)
    require('WRITER.LEASED' in allowed['hookSpecificOutput']['additionalContext'], 'owner not leased')
    require(denied['hookSpecificOutput']['permissionDecision'] == 'deny', 'competitor not denied')
    conflict_event = [e for e in gate.events if e['event'] == 'published' and Path(e['path']).parent.name == 'writer_conflict']
    returned = [e for e in gate.events if e['event'] == 'blocked_return'][0]
    require(len(conflict_event) == 1 and conflict_event[0]['time_ns'] < returned['time_ns'], 'conflict not durable before deny')
    conflict = conflict_event[0]['value']
    require(conflict['tool_use_id'] == second['tool_use_id'] and conflict['paths'] == ['owned/result.txt'], 'wrong conflict identity')
    # No mutation dispatched in this controlled schedule; release must match
    # the exact actor/call. An incorrect callback cannot clear the lease.
    wrong = fixture.writer_lease_guard.post_tool_use(f.store, f.parent_patch_hook(event='PostToolUse', tool_use_id='wrong-call'))
    require(len(list((f.store.root / 'writer_claim').glob('*.json'))) == 1, 'wrong callback cleared lease')
    correct = fixture.writer_lease_guard.post_tool_use(f.store, f.parent_patch_hook(event='PostToolUse', tool_use_id='held-parent-call'))
    require(correct == {} and not list((f.store.root / 'writer_claim').glob('*.json')), 'exact release failed')
    successor = fixture.writer_lease_guard.pre_tool_use(f.store, f.parent_patch_hook(tool_use_id='successor-call'))
    require('WRITER.LEASED' in successor['hookSpecificOutput']['additionalContext'], 'stale claim blocked successor')
    fixture.writer_lease_guard.post_tool_use(f.store, f.parent_patch_hook(event='PostToolUse', tool_use_id='successor-call'))
    return {'schedule': 'parent_exact_claim_conflict_then_release', 'root': str(f.root),
            'git_snapshot': fixture.runtime_guard.collect_git_snapshot(f.repository),
            'events': gate.events, 'wrong_callback': wrong, 'state': states(f.store),
            'mutation_dispatch_count': 0, 'result': 'durable_deny_before_return_then_exact_release'}


def crash_recovery():
    f = make_fixture()
    hook = f.parent_patch_hook(tool_use_id='crashed-holder-call')
    request = f.root / 'crash-request.json'
    request.write_text(json.dumps({'state': str(f.store.root), 'hook': hook}), encoding='utf-8')
    completed = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--crash-holder', str(request)],
                               capture_output=True, text=True, timeout=30)
    require(completed.returncode == 23, 'holder did not exit at the explicit crash boundary: ' + completed.stderr)
    claim_path = next((f.store.root / 'writer_claim').glob('*.json'))
    claim = f.store.read_writer_claim(claim_path.stem)
    before = states(f.store)
    # Parent and a distinct sibling must both be denied after process death;
    # a dead process or elapsed time alone never releases persisted authority.
    sibling = f.child_hook('sibling')
    sibling.update({key: value for key, value in f.parent_patch_hook(tool_use_id='sibling-blocked-call').items()
                    if key in ('hook_event_name', 'tool_name', 'tool_input', 'tool_use_id')})
    denied = []
    for contender in (f.parent_patch_hook(tool_use_id='parent-after-crash'), sibling):
        result = fixture.writer_lease_guard.pre_tool_use(f.store, contender)
        require(result['hookSpecificOutput']['permissionDecision'] == 'deny', 'crash freed authority implicitly')
        conflict = [json.loads(p.read_text()) for p in (f.store.root / 'writer_conflict').glob('*.json')
                    if json.loads(p.read_text())['tool_use_id'] == contender['tool_use_id']]
        require(len(conflict) == 1 and any(c['kind'] == 'writer_claim' and c['claim_id'] == claim['claim_id']
                                         for c in conflict[0]['conflicts']), 'durable claim conflict absent at return')
        denied.append({'hook': contender, 'result': result, 'durable_conflict': conflict[0], 'return_ns': time.time_ns()})
    actor = fixture.writer_lease_guard.actor_identity_from_hook(hook)
    receipt = f.store.abort_unchanged_writer_claim(actor, claim_id=claim['claim_id'],
        after_snapshot=fixture.runtime_guard.collect_git_snapshot(f.repository),
        recovery_reason='missing_posttooluse_after_tool_failure')
    require(not claim_path.exists() and receipt.is_file(), 'explicit unchanged recovery failed')
    new_hook = f.parent_patch_hook(tool_use_id='after-explicit-recovery')
    result = fixture.writer_lease_guard.pre_tool_use(f.store, new_hook)
    require('WRITER.LEASED' in result['hookSpecificOutput']['additionalContext'], 'stale claim survived recovery')
    fixture.writer_lease_guard.post_tool_use(f.store, f.parent_patch_hook(event='PostToolUse', tool_use_id='after-explicit-recovery'))
    return {'schedule': 'actual_holder_process_exit_then_durable_deny_and_unchanged_recovery',
            'root': str(f.root), 'holder_exit_code': completed.returncode, 'before': before,
            'denied': denied, 'abort': json.loads(receipt.read_text()), 'state': states(f.store),
            'mutation_dispatch_count': 0, 'result': 'fail_closed_until_exact_recovery'}


def expiry():
    f = make_fixture()
    require('HANDOFF.STAGED' in f.capture(spawn(f, 'expiry'))['hookSpecificOutput']['additionalContext'], 'capture failed')
    child = f.child_hook('expiry')
    fixture.assignment_transport.subagent_start(f.store, child)
    assignment_id, envelope = f.store.list_active()[0]
    # The watchdog exposes an explicit clock input. Test both sides of the
    # exact deadline without sleeping or modifying persisted timestamps.
    deadline = dt.datetime.fromisoformat(envelope['capsule']['pre_write_attestation_deadline'])
    before = fixture.runtime_guard.sweep_deadlines(f.store, now=deadline, assignment_ids={assignment_id})
    require(before == [] and f.store.path('active', assignment_id).exists(), 'deadline boundary drift')
    after = fixture.runtime_guard.sweep_deadlines(f.store, now=deadline + dt.timedelta(microseconds=1), assignment_ids={assignment_id})
    require(len(after) == 1 and not f.store.path('active', assignment_id).exists(), 'expired authority stayed active')
    child.update(hook_event_name='PreToolUse', tool_name='apply_patch', tool_use_id='expired-call',
                 tool_input={'command': '*** Begin Patch\n*** Add File: owned/expiry/result.txt\n+forbidden\n*** End Patch'})
    result = fixture.runtime_guard.pre_tool_use(f.store, child, now=deadline + dt.timedelta(microseconds=2))
    require(result['hookSpecificOutput']['permissionDecision'] == 'deny', 'expired child retained authority')
    return {'schedule': 'exact_deadline_then_expiry', 'root': str(f.root), 'clock_domain': 'explicit watchdog now parameter',
            'deadline': deadline.isoformat(), 'termination': after, 'denial': result,
            'state': states(f.store), 'mutation_dispatch_count': 0, 'result': 'no_stale_active_authority'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--crash-holder', type=Path)
    args = parser.parse_args()
    if args.crash_holder:
        request = json.loads(args.crash_holder.read_text())
        store = fixture.StateStore(Path(request['state']))
        result = fixture.writer_lease_guard.pre_tool_use(store, request['hook'])
        require('WRITER.LEASED' in result['hookSpecificOutput']['additionalContext'], 'crash holder not leased')
        os._exit(23)
    require(args.output is not None, 'output required')
    require(not args.output.exists(), 'output already exists')
    result = {'schema': 1, 'classification': 'controlled_real_state_store_schedules',
              'native_agent_live': False, 'historical_failures_explained': False,
              'direct_write_qualified': False, 'phase1_complete': False, 'p7_complete': False,
              'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in
                                [Path(__file__), ROOT / 'tests/test_assignment_transport.py', *sorted((ROOT / 'hooks').glob('*.py'))]},
              'schedules': []}
    try:
        for bucket in ('pending', 'claimed', 'active'):
            result['schedules'].append(binding(bucket))
        result['schedules'].append(writer())
        result['schedules'].append(crash_recovery())
        result['schedules'].append(expiry())
        result['passed'] = True
    except Exception as error:
        result['passed'] = False
        result['error'] = repr(error)
        raise
    finally:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({'passed': True, 'schedules': len(result['schedules']), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
