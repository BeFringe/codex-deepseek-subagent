"""Fresh-process owner verification of the bounded native Windows read-only run.

No overall timeout, incomplete callback, unknown catalog, or missing termination receipt
can consume authority. This is not a general process-tree or write qualification.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from run_p7_windows_live import ROOT, BASE, SOURCE_PATCHES, ROLE, PROVIDERS, digest, invocation, snapshot
from adjudicate_g4_sibling_admission_live import (
    AdjudicationError, StateError, StateStore, assistant_final, attestation_from,
    callback_payload, catalog_receipts, one, output_for, read_json, read_jsonl,
    registered_names, require, response_payloads, session_meta,
)
from hook_event_receipts import load_chain, observation_from_hook
from p7_windows_acl import run_directory_acl
from p7_current_candidate_source import CUMULATIVE, verify_current_source


def messages(records, role):
    return [part['text'] for item in response_payloads(records, 'message')
            if item.get('role') == role for part in item.get('content', [])
            if isinstance(part, dict) and isinstance(part.get('text'), str)]


def verify_close(close, child_id, canonical):
    require(close.get('target_thread_id') == child_id
            and close.get('target_agent_path') == canonical, 'close identity mismatch')
    for field in ('session_loop_terminated', 'model_callable_process_bootstrap_absent',
                  'tracked_process_termination_confirmed', 'closed_catalog_actor_quiescence_claimed'):
        require(close.get(field) is True, 'close barrier missing: ' + field)
    require(close.get('tracked_background_processes_before_close') == 0,
            'unexpected tracked background process')
    for field in ('tracked_process_ids_by_thread', 'confirmed_exit_process_ids_by_thread',
                  'unconfirmed_exit_process_ids_by_thread', 'unresolved_start_process_ids_by_thread'):
        require(close.get(field) == {child_id: []}, 'close map not exact: ' + field)
    require(close.get('process_tree_quiescence_claimed') is False,
            'bounded receipt cannot claim global process-tree quiescence')


def child_namespace(provider):
    require(provider in PROVIDERS, 'unknown provider catalog profile')
    return None if provider == 'deepseek' else 'g4_assignment'


def verify_catalog(path, provider):
    rows = catalog_receipts(path)
    require(rows, 'closed catalog receipts absent')
    common = {'apply_patch', 'view_image'}
    expected = {
        'qualification_parent': common | {'g4_assignment.' + name for name in
            ('spawn_agent', 'send_message', 'followup_task', 'close_agent',
             'interrupt_agent', 'list_agents', 'wait_agent')},
        # These third-party models use fallback ModelInfo (apply_patch=None).
        # spec_plan.rs registers apply_patch only when the model enables it.
        'qualification_child': {'view_image',
            ('g4_assignment.' if child_namespace(provider) else '') + 'list_agents'},
    }
    require({row.get('actor_kind') for row in rows} == set(expected), 'catalog actor set mismatch')
    for row in rows:
        names = registered_names(row)
        require(len(names) == len(set(names)) and set(names) == expected[row['actor_kind']],
                'native tool catalog widened or missing')
        require(row['catalog'].get('code_mode_tool_names') == {}, 'code mode remains callable')
        require(row['catalog'].get('can_manage_children') is
                (row['actor_kind'] == 'qualification_parent'), 'child management capability mismatch')


def verify(manifest_path):
    manifest = read_json(manifest_path)
    require(os.name == 'nt' and manifest['platform']['system'] == 'Windows', 'not native Windows')
    require(manifest.get('classification') == 'p7_windows_native_raw_attempt', 'wrong manifest kind')
    require(manifest.get('runner_pid') != os.getpid(), 'adjudicator must be a fresh process')
    require(manifest.get('exit_code') == 0 and not manifest.get('timeout')
            and manifest.get('prepared_only') is False, 'native run did not finish normally')
    require(manifest.get('credential_present') is True
            and manifest.get('credential_values_recorded') is False
            and manifest.get('isolated_auth_removed') is True, 'credential boundary missing')
    provider = manifest['provider']
    require(provider in PROVIDERS and manifest['model'] == PROVIDERS[provider]['model'], 'route mismatch')
    require(digest(manifest['candidate']) == manifest['candidate_sha256'], 'binary drift')
    require(digest(manifest['build_receipt']) == manifest['build_receipt_sha256'], 'build receipt drift')
    build = read_json(Path(manifest['build_receipt']))
    verify_current_source(ROOT, Path(build['source_root']), build)
    require(build['source_commit'] == BASE and build['patch_sha256'] in SOURCE_PATCHES
            and build['candidate_sha256'] == manifest['candidate_sha256']
            and build['exit_code'] == 0 and build['target'] == 'x86_64-pc-windows-msvc',
            'source/build identity mismatch')
    directory = manifest_path.resolve().parent
    require(run_directory_acl(directory) == manifest['run_directory_acl'], 'private run-root DACL drift')
    require(manifest['argv'] == invocation(Path(manifest['candidate']), Path(manifest['root']),
            directory / 'role.toml', provider), 'candidate invocation drift')
    require(digest(Path(manifest['home']) / 'hooks.json') == manifest['hooks_config_sha256'],
            'Hook registry drift')
    for name in ('run_p7_windows_live.py', 'p7_windows_hook.py', 'p7_windows_acl.py',
                 'adjudicate_p7_windows_live.py', 'build_g4_native_probe_prompt.py'):
        require(digest(ROOT / 'probes' / name) == manifest['harness_sha256'][name], 'harness drift: ' + name)
    if build['patch_sha256'] == CUMULATIVE:
        require(digest(ROOT / 'probes/p7_current_candidate_source.py') ==
                manifest['harness_sha256'].get('p7_current_candidate_source.py'),
                'complete source verifier drift')
    for path in (ROOT / 'hooks').glob('*.py'):
        require(digest(path) == digest(directory / 'hook-runtime' / path.name), 'Hook implementation drift')
    for relative, expected_hash in manifest['artifacts'].items():
        path = (directory / relative).resolve(strict=True)
        require(path.is_relative_to(directory), 'artifact escaped run directory')
        require(digest(path) == expected_hash, 'artifact drift: ' + relative)
    root = Path(manifest['root']).resolve(strict=True)
    require(root == directory / 'worktree', 'probe root escaped its isolated directory')
    require(Path(manifest['state']).resolve() == directory / 'state', 'state escaped run directory')
    live_state_files = {path.relative_to(directory / 'state').as_posix(): digest(path)
                       for path in (directory / 'state').rglob('*') if path.is_file()}
    require(live_state_files and live_state_files == manifest['state_snapshot_files'],
            'live authority state differs from the retained pre-adjudication snapshot')
    require(not manifest['baseline']['status'], 'baseline was dirty')
    require(manifest['process_exited_ns'] < manifest['barrier_first']['observed_ns']
            < manifest['barrier_second']['observed_ns'], 'post-exit barrier order mismatch')
    require(manifest['barrier_second']['observed_ns'] - manifest['barrier_first']['observed_ns']
            >= 2_000_000_000, 'post-exit observation interval too short')
    for barrier in ('barrier_first', 'barrier_second'):
        require(manifest[barrier]['snapshot'] == manifest['baseline'], 'post-exit disk changed')
    require(snapshot(root) == manifest['baseline'], 'fresh disk observation changed')
    verify_catalog(directory / 'stderr.log', provider)

    rollouts = [read_jsonl(path) for path in (directory / 'rollouts').glob('*.jsonl')]
    require(len(rollouts) == 2, 'expected exactly parent and child rollouts')
    for rows in rollouts:
        require(rows and rows[0].get('type') == 'session_meta', 'SessionMeta is not first record')
    parent_rows = one([rows for rows in rollouts if session_meta(rows, 'actor').get('source') == 'exec'], 'parent')
    child_rows = one([rows for rows in rollouts if rows is not parent_rows], 'child')
    parent, child = session_meta(parent_rows, 'parent'), session_meta(child_rows, 'child')
    parent_id, child_id = parent['id'], child['id']
    canonical = '/root/' + manifest['requested_task_name']
    require(parent_id != child_id and parent.get('session_id') == parent_id
            and parent.get('model_provider') == 'openai', 'parent identity/provider mismatch')
    require(child.get('session_id') == parent_id and child.get('parent_thread_id') == parent_id
            and child.get('model_provider') == provider and child.get('agent_role') == ROLE
            and child.get('agent_path') == canonical, 'child identity/provider mismatch')
    for meta in (parent, child):
        require(Path(meta['cwd']).resolve() == root and meta.get('cli_version') == '0.153.4',
                'runtime root/version mismatch')
    edge = child.get('source', {}).get('subagent', {}).get('thread_spawn', {})
    require(edge.get('parent_thread_id') == parent_id and edge.get('depth') == 1
            and edge.get('agent_path') == canonical and edge.get('agent_role') == ROLE,
            'native spawn edge mismatch')
    contexts = [row['payload'] for row in child_rows if row.get('type') == 'turn_context']
    require(contexts and all(context.get('model') == manifest['model'] for context in contexts),
            'child model lacks native TurnContext evidence')
    for context in contexts:
        require(context.get('sandbox_policy', {}).get('type') == 'read-only',
                'child TurnContext read-only permission receipt absent')

    calls = response_payloads(parent_rows, 'function_call')
    names = [call.get('name') for call in calls]
    require(len(calls) >= 4 and names[0] == 'spawn_agent'
            and names[-2:] == ['close_agent', 'list_agents']
            and all(name == 'wait_agent' for name in names[1:-2]), 'unexpected parent tool sequence')
    require(all(call.get('namespace') == 'g4_assignment' for call in calls), 'parent namespace drift')
    spawn, close_call, listed = calls[0], calls[-2], calls[-1]
    arguments = json.loads(spawn['arguments'])
    require(set(arguments) == {'agent_type', 'task_name', 'fork_turns', 'message'}
            and arguments['agent_type'] == ROLE and arguments['fork_turns'] == 'none'
            and arguments['task_name'] == manifest['requested_task_name'], 'spawn arguments mismatch')
    require(arguments['message'] == (directory / 'assignment.txt').read_text(encoding='utf-8'),
            'native spawn did not preserve the prepared plaintext assignment')
    require(json.loads(output_for(parent_rows, spawn['call_id'])) == {'task_name': canonical}, 'spawn result mismatch')
    wait_timeouts = [json.loads(output_for(parent_rows, wait['call_id'])).get('timed_out')
                     for wait in calls[1:-2]]
    require(all(isinstance(value, bool) for value in wait_timeouts)
            and wait_timeouts[-1] is False, 'native wait did not reach completion')
    tool = one(response_payloads(child_rows, 'function_call'), 'child tool')
    require(tool.get('name') == 'list_agents' and tool.get('namespace') == child_namespace(provider),
            'child tool does not match the exact provider namespace profile')
    require(json.loads(tool['arguments']) == {}, 'child list_agents arguments must be exactly empty')
    require(json.loads(output_for(child_rows, tool['call_id'])) == {'agents': [
        {'agent_name': '/root', 'agent_status': 'running'},
        {'agent_name': canonical, 'agent_status': 'running'}]}, 'child tool result mismatch')
    final = assistant_final(child_rows)
    require(callback_payload(parent_rows) == final, 'callback differs from child final')
    attestation = attestation_from(final)
    require(json.loads(close_call['arguments']) == {'target': canonical}, 'close target mismatch')
    close = json.loads(output_for(parent_rows, close_call['call_id']))
    verify_close(close, child_id, canonical)
    require(json.loads(output_for(parent_rows, listed['call_id'])) == {
        'agents': [{'agent_name': '/root', 'agent_status': 'running'}]}, 'closed child remains live')
    # Position in the raw parent stream binds callback-before-close and close
    # output-before-list. Repeated output IDs are rejected by output_for.
    response = response_payloads(parent_rows, 'message')
    callback = one([item for item in response if item.get('role') == 'user'
                   and any(part.get('text', '').startswith('Message Type: FINAL_ANSWER\n')
                           for part in item.get('content', []))], 'callback message')
    payloads = [row.get('payload') for row in parent_rows]
    close_output = one([item for item in response_payloads(parent_rows, 'function_call_output')
                       if item.get('call_id') == close_call['call_id']], 'close output')
    require(payloads.index(callback) < payloads.index(close_call)
            < payloads.index(close_output) < payloads.index(listed), 'callback/termination order mismatch')

    events = [read_json(path) for path in (directory / 'hook-events').glob('*.json')]
    for event in events:
        raw = event['stdin_utf8'].encode('utf-8')
        require(event.get('exit_code') == 0 and 'observer_error' not in event
                and event['stdin_bytes'] == len(raw)
                and event['stdin_sha256'] == hashlib.sha256(raw).hexdigest()
                and json.loads(raw) == event['input'], 'Hook byte/exit evidence mismatch')
        require(event['finished_ns'] < manifest['process_exited_ns'], 'Hook persisted past candidate exit')
        require('TASK.CONTEXT_LOST' not in event['stdout'], 'Hook lost assignment context')
        output = json.loads(event['stdout']) if event['stdout'].strip() else {}
        require(output.get('hookSpecificOutput', {}).get('permissionDecision') != 'deny'
                and output.get('decision') != 'block', 'Hook denied this attempt')
    start = one([event for event in events if event['input'].get('hook_event_name') == 'SubagentStart'], 'SubagentStart')
    context = json.loads(start['stdout'])['hookSpecificOutput']['additionalContext']
    require(any(context in text for text in messages(child_rows, 'developer')),
            'SubagentStart context absent from native rollout')
    require(context.split('BEGIN PARENT ASSIGNMENT\n', 1)[1].rsplit('\nEND PARENT ASSIGNMENT', 1)[0]
            == arguments['message'], 'plaintext assignment drifted')
    store = StateStore(Path(manifest['state']))
    chain = load_chain(manifest['state'])
    observations = []
    for event in sorted(events, key=lambda item: item['started_ns']):
        observed = observation_from_hook(event['input'], plaintext_agent_types={ROLE})
        if observed is not None:
            observations.append(observed)
    require([event['hook_event_name'] for event in observations]
            == ['PreToolUse', 'SubagentStart', 'PreToolUse', 'SubagentStop'],
            'Hook lifecycle is not exact spawn/start/tool/stop')
    require(len(chain['events']) == len(observations), 'durable/raw Hook count mismatch')
    for durable, observed in zip(chain['events'], observations):
        require(all(durable.get(key) == value for key, value in observed.items()),
                'durable/raw Hook observation mismatch')
    require(observations[0]['actor']['thread_id'] == parent_id
            and observations[0]['tool_use_id'] == spawn['call_id'], 'spawn Hook identity mismatch')
    for observed in observations[1:]:
        actor = observed['actor']
        require(actor['thread_id'] == child_id and actor['runtime_session_id'] == parent_id
                and actor['canonical_agent_path'] == canonical and actor['agent_type'] == ROLE,
                'child Hook identity mismatch')
    require(observations[2]['tool_use_id'] == tool['call_id'], 'child tool Hook identity mismatch')
    reported = one(list((Path(manifest['state']) / 'reported').glob('*.json')), 'reported authority')
    envelope = read_json(reported)
    capsule, binding = envelope['capsule'], envelope['binding']
    assignment_id = capsule['assignment_id']
    require(envelope['assignment'] == arguments['message'] and envelope['final_attestation'] == attestation,
            'durable report differs from raw assignment/final')
    require(capsule['runtime_session_id'] == parent_id and capsule['parent_thread_id'] == parent_id
            and capsule['canonical_agent_path'] == canonical and binding['child_thread_id'] == child_id
            and capsule['spawn_tool_use_id'] == spawn['call_id'], 'authority native binding mismatch')
    require(capsule['assignment_mutation_mode'] == 'read_only' and capsule['owned_paths'] == []
            and not any(capsule['git_authority'].values())
            and capsule['parent_recorded_user_write_intent'] == 'deny', 'authority widened')
    require(snapshot(root) == manifest['baseline'], 'final pre-consumption disk drift')
    return manifest, store, assignment_id, {'parent_thread_id': parent_id, 'child_thread_id': child_id,
        'canonical_agent_path': canonical, 'close_receipt': close, 'callback_byte_exact': True,
        'child_tool_name': tool['name'], 'child_tool_namespace': tool.get('namespace'),
        'child_tool_arguments': json.loads(tool['arguments']), 'child_tool_call_id': tool['call_id'],
        'child_tool_output_sha256': hashlib.sha256(output_for(child_rows, tool['call_id']).encode('utf-8')).hexdigest(),
        'callback_sha256': hashlib.sha256(final.encode('utf-8')).hexdigest(),
        'raw_hook_event_count': len(events), 'durable_hook_event_count': len(observations),
        'interim_wait_timeouts': sum(wait_timeouts)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), 'adjudication output already exists')
        manifest, store, assignment_id, evidence = verify(args.manifest)
        adjudication = {field: 'pass' for field in ('location_integrity', 'mutation_scope_integrity',
            'verification_freshness', 'derivation_provenance_integrity', 'feasibility_contract_integrity')}
        adjudication['evidence_sha256'] = digest(args.manifest)
        consumed = store.adjudicate_parent(assignment_id, adjudication)
        require(consumed == store.path('consumed', assignment_id) and consumed.is_file(), 'consumption failed')
        require(not any(store.path(bucket, assignment_id).exists()
                        for bucket in ('active', 'reported', 'unresolved')), 'authority remains live')
        result = {'schema': 1, 'classification': 'p7_windows_fresh_owner_readonly_lifecycle',
            'fresh_adjudicator_pid': os.getpid(), 'manifest_sha256': digest(args.manifest),
            'provider': manifest['provider'], 'identity_and_lifecycle': evidence,
            'assignment_id': assignment_id, 'consumed_sha256': digest(consumed),
            'windows_live_qualified': True, 'scope': 'exact closed native parent and read-only child',
            'global_process_tree_qualified': False, 'direct_write_qualified': False,
            'phase1_complete': False, 'phase2_state': 'closed', 'phase3_state': 'closed'}
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'qualified': True, 'output': str(args.output)}))
        return 0
    except (AdjudicationError, StateError, OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({'qualified': False, 'error_type': type(error).__name__, 'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
