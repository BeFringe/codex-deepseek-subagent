"""One bounded native Windows G4 child run; only a fresh owner can qualify it."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

from build_g4_native_probe_prompt import build_prompt
from p7_windows_acl import run_directory_acl


ROOT = Path(__file__).resolve().parents[1]
ROLE = 'g4_qualification_probe_worker'
BASE = '3d2ee51ca2d5db578f328aa75e20aa22c0197c9a'
PATCH_HASH = '94ec3d6140868055662ca43b0d0d464f5bda8d41cd40433a20facb4fb600f72d'
SOURCE_PATCHES = {
    PATCH_HASH: 'current-signed-runtime-g4-cumulative-source-candidate.patch',
    '4f61f37ae46f6160055fde7b7ce95d095b2456ce1b9f1a96f5947669baab63b8':
        'current-signed-runtime-g4-custom-tool-pairing-source-candidate.patch',
}
REPO_HEAD = '785b945d46a9a8879f659a428ff0a03d940cf7a1'
PROVIDERS = {
    'deepseek': {'model': 'deepseek-v4-flash', 'base_url': 'https://api.deepseek.com',
                 'env_key': 'DEEPSEEK_API_KEY'},
    'zhipu': {'model': 'glm-5.3', 'base_url': 'https://open.bigmodel.cn/api/v1',
              'env_key': 'ZHIPU_API_KEY'},
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


def git(root, *args):
    return command(['git', '--no-optional-locks', '-C', str(root), *args]).stdout.decode('utf-8').strip()


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def snapshot(root):
    tracked = command(['git', '-C', str(root), 'ls-files', '-z']).stdout
    paths = [name.decode('utf-8') for name in tracked.split(b'\0') if name]
    return {
        'root': str(root.resolve()), 'branch': git(root, 'symbolic-ref', '--short', 'HEAD'),
        'head': git(root, 'rev-parse', 'HEAD'),
        'status': git(root, 'status', '--short', '--untracked-files=all'),
        'index_sha256': hashlib.sha256(command(
            ['git', '-C', str(root), 'ls-files', '--stage', '-z']).stdout).hexdigest(),
        'files': {name: digest(root / name) for name in paths},
    }


def invocation(candidate, root, role, provider):
    route = PROVIDERS[provider]
    overrides = {
        'model_provider': 'openai',
        'forced_login_method': 'chatgpt',
        'features.multi_agent_v2.enabled': True,
        'features.multi_agent_v2.message_delivery': 'plaintext',
        'features.multi_agent_v2.tool_namespace': 'g4_assignment',
        f'features.multi_agent_v2.child_model_providers.{ROLE}': provider,
        f'agents.{ROLE}.config_file': str(role),
        f'model_providers.{provider}.name': 'P7 ' + provider,
        f'model_providers.{provider}.base_url': route['base_url'],
        f'model_providers.{provider}.env_key': route['env_key'],
        f'model_providers.{provider}.wire_api': 'responses',
        f'model_providers.{provider}.requires_openai_auth': False,
        f'model_providers.{provider}.request_max_retries': 0,
        f'model_providers.{provider}.stream_max_retries': 0,
        'features.code_mode_host': False,
    }
    if provider == 'deepseek':
        overrides['model_providers.deepseek.supports_namespace_tools'] = False
        overrides['model_providers.deepseek.requires_function_call_output_adjacency'] = True
    result = [str(candidate)]
    for key, value in overrides.items():
        result += ['-c', key + '=' + json.dumps(value)]
    result += ['-a', 'never', '-s', 'read-only', 'exec', '--ignore-user-config',
               '--ignore-rules', '--dangerously-bypass-hook-trust', '--json', '-C', str(root), '-']
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--artifacts-parent', type=Path, required=True)
    parser.add_argument('--provider', choices=PROVIDERS, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    require(os.name == 'nt', 'native Windows is required')
    require('CODEX_CLI_PATH' not in os.environ, 'CODEX_CLI_PATH must be absent')
    # Codex gives this process override precedence over the saved ChatGPT login.
    # Remove it only in this runner; never read or persist the credential value.
    parent_api_key_override_removed = 'CODEX_API_KEY' in os.environ
    if parent_api_key_override_removed:
        del os.environ['CODEX_API_KEY']
    require(PROVIDERS[args.provider]['env_key'] in os.environ, 'provider credential is absent')
    checkout_head = git(ROOT, 'rev-parse', 'HEAD')
    require(git(ROOT, 'merge-base', REPO_HEAD, checkout_head) == REPO_HEAD,
            'qualification checkout is not based on the pinned commit')
    build = json.loads(args.build_receipt.read_text(encoding='utf-8'))
    require(build['source_commit'] == BASE and build['patch_sha256'] in SOURCE_PATCHES,
            'build source identity mismatch')
    require(digest(ROOT / 'probes' / SOURCE_PATCHES[build['patch_sha256']]) == build['patch_sha256'],
            'pinned source patch artifact drift')
    require(build['exit_code'] == 0 and build['target'] == 'x86_64-pc-windows-msvc',
            'successful native Windows build receipt required')
    candidate = Path(build['candidate']).resolve(strict=True)
    require(digest(candidate) == build['candidate_sha256'], 'candidate hash mismatch')
    require(command([str(candidate), '--version']).stdout.decode().strip() == 'codex-cli 0.153.4',
            'candidate semantic version mismatch')
    source = Path(build['source_root'])
    require(git(source, 'rev-parse', 'HEAD') == BASE, 'source checkout HEAD drift')
    replay = command(['git', '-C', str(source), 'diff', '--binary', '--full-index', 'HEAD']).stdout
    require(hashlib.sha256(replay).hexdigest() == build['patch_sha256'], 'source patch replay drift')

    run_id = 'p7-' + args.provider + '-' + uuid.uuid4().hex
    artifacts = args.artifacts_parent.resolve(strict=True) / run_id
    artifacts.mkdir()
    acl_receipt = run_directory_acl(artifacts, secure=True)
    root = artifacts / 'worktree'
    (root / 'docs').mkdir(parents=True)
    (root / 'docs' / 'phase1-evidence.md').write_text(
        'Product-independent Windows read-only native lifecycle fixture.\n', encoding='utf-8')
    git(root, 'init', '-b', 'main')
    git(root, 'add', 'docs/phase1-evidence.md')
    git(root, '-c', 'user.name=P7 qualification', '-c', 'user.email=p7@invalid',
        'commit', '-m', 'Windows lifecycle fixture')
    baseline = snapshot(root)
    require(not baseline['status'], 'probe baseline must be clean')
    state = artifacts / 'state'
    events = artifacts / 'hook-events'
    events.mkdir()
    runtime = artifacts / 'hook-runtime'
    runtime.mkdir()
    for path in (ROOT / 'hooks').glob('*.py'):
        shutil.copyfile(path, runtime / path.name)
    observer = runtime / 'p7_windows_hook.py'
    shutil.copyfile(ROOT / 'probes' / observer.name, observer)
    role = artifacts / 'role.toml'
    role.write_text((ROOT / 'agents' / 'g4-qualification-probe-worker.toml').read_text(
        encoding='utf-8') + '\nmodel = ' + json.dumps(PROVIDERS[args.provider]['model']) + '\n',
        encoding='utf-8')
    task_name = 'p7_windows_' + args.provider
    prompt = build_prompt(root, task_name)
    insertion = (
        'Use timeout_ms=120000 for native wait_agent. An interim wait timeout is '
        'not completion; keep waiting for the exact final callback within the run budget. '
        'After receiving the exact child final callback, call g4_assignment.close_agent '
        f'exactly once with target=/root/{task_name}. Require session_loop_terminated, '
        'tracked_process_termination_confirmed and closed_catalog_actor_quiescence_claimed '
        'all true, and empty tracked/unconfirmed/unresolved process lists for every '
        'captured thread. Then call g4_assignment.list_agents exactly once and verify '
        'the child is no longer live. Report any missing field as a failure. '
        'Do not make another spawn or follow-up.\n\n'
    )
    prompt = prompt.replace('EXACT CHILD ASSIGNMENT:\n', insertion + 'EXACT CHILD ASSIGNMENT:\n', 1)
    final_shape = (
        'Call g4_assignment.list_agents exactly once with arguments {}. Do not set path_prefix. '
        'Emit exactly one final answer: a plain-text attestation envelope. '
        'Its first characters must be BEGIN CODEX WORKER ATTESTATION and its last '
        'characters must be END CODEX WORKER ATTESTATION. Never use Markdown '
        'backticks, code fences, a language label, or any surrounding prose. '
        'Final-attestation shape: root, branch, head, index_changed, git_status_short, '
        'and changed_paths MUST be top-level JSON keys. Do not wrap them in git_facts '
        'or use head_oid. Do not add schema. The complete top-level key set is '
        'assignment_id, handoff_id, capsule_sha256, compact_invariant_sha256, '
        'canonical_agent_path, recovery_count, root, branch, head, index_changed, '
        'git_status_short, changed_paths, authority_provenance, verification, '
        'inventory_summaries, context_lost, authority_violation, assigned_slice_complete. '
        'Use the Hook-delivered values and the tool result; never invent evidence.\n\n'
    )
    prompt = prompt.replace('EXACT CHILD ASSIGNMENT:\n\n',
                            'EXACT CHILD ASSIGNMENT:\n\n' + final_shape, 1)
    (artifacts / 'prompt.txt').write_text(prompt, encoding='utf-8', newline='\n')
    assignment = prompt.split('EXACT CHILD ASSIGNMENT:\n\n', 1)[1].removesuffix('\n')
    (artifacts / 'assignment.txt').write_text(assignment, encoding='utf-8', newline='\n')
    # Same-volume hardlink shares the existing login without reading/copying its
    # contents. No auth path is included in raw artifact hashing or collection.
    auth = Path.home() / '.codex' / 'auth.json'
    require(auth.is_file(), 'current ChatGPT login file is absent')
    home = Path.home() / '.codex-p7-qualification' / run_id
    home.mkdir(parents=True)
    hook_args = [sys.executable, str(observer), '--guard', str(runtime / 'compatibility_hook.py'),
                 '--state', str(state), '--events', str(events)]
    require(not any(any(c in arg for c in '&|<>^%!') for arg in hook_args),
            'Hook path requires unsupported shell escaping')
    hooks = json.loads((ROOT / 'hooks' / 'hooks.g4-qualification.posix.example.json').read_text())
    for groups in hooks['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                hook['command'] = subprocess.list2cmdline(hook_args)
                hook['timeout'] = 30
    write_json(home / 'hooks.json', hooks)
    argv = invocation(candidate, root, role, args.provider)
    manifest = {
        'schema': 1, 'classification': 'p7_windows_native_raw_attempt',
        'runner_pid': os.getpid(), 'run_id': run_id, 'provider': args.provider,
        'qualification_base_commit': REPO_HEAD, 'qualification_checkout_head': checkout_head,
        'run_directory_acl': acl_receipt,
        'model': PROVIDERS[args.provider]['model'], 'requested_task_name': task_name,
        'platform': {'system': platform.system(), 'release': platform.release(),
                     'version': platform.version(), 'machine': platform.machine()},
        'build_receipt': str(args.build_receipt.resolve()),
        'build_receipt_sha256': digest(args.build_receipt), 'baseline': baseline,
        'candidate': str(candidate), 'candidate_sha256': digest(candidate),
        'root': str(root), 'state': str(state), 'home': str(home),
        'hook_events': str(events), 'argv': argv,
        'credential_present': True, 'credential_values_recorded': False,
        'parent_api_key_override_removed': parent_api_key_override_removed,
        'prepared_only': args.prepare_only, 'windows_live_qualified': False,
        'phase1_complete': False, 'direct_write_qualified': False,
        'harness_sha256': {name: digest(ROOT / 'probes' / name) for name in
            ('run_p7_windows_live.py', 'p7_windows_hook.py', 'p7_windows_acl.py',
             'adjudicate_p7_windows_live.py', 'build_g4_native_probe_prompt.py')},
    }
    write_json(artifacts / 'prepared.json', manifest)
    if args.prepare_only:
        print(artifacts / 'prepared.json')
        return 0
    os.environ['CODEX_HOME'] = str(home)
    os.environ['CODEX_G4_TOOL_CATALOG_RECEIPT'] = 'stderr-v2-parent-child-closed'
    os.link(auth, home / 'auth.json')
    manifest['started_ns'] = time.time_ns()
    try:
        with (artifacts / 'stdout.jsonl').open('wb') as stdout, (artifacts / 'stderr.log').open('wb') as stderr:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
            manifest['candidate_pid'] = process.pid
            try:
                process.communicate(prompt.encode('utf-8'), timeout=600)
                manifest['exit_code'] = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=30)
                manifest['exit_code'] = process.returncode
                manifest['timeout'] = True
    finally:
        # Remove only this run's link; the original current login is retained.
        (home / 'auth.json').unlink(missing_ok=True)
        manifest['isolated_auth_removed'] = True
    manifest['process_exited_ns'] = time.time_ns()
    # Windows wall-clock resolution can make adjacent time_ns calls identical.
    # Timestamp completed observations, after an explicit separation from exit.
    time.sleep(0.05)
    first_snapshot = snapshot(root)
    manifest['barrier_first'] = {'observed_ns': time.time_ns(), 'snapshot': first_snapshot}
    time.sleep(2.05)
    second_snapshot = snapshot(root)
    manifest['barrier_second'] = {'observed_ns': time.time_ns(), 'snapshot': second_snapshot}
    rollouts = artifacts / 'rollouts'
    rollouts.mkdir()
    for path in (home / 'sessions').rglob('*.jsonl'):
        shutil.copyfile(path, rollouts / path.name)
    # Owner adjudication consumes the live reported envelope. Retain the exact
    # pre-adjudication bytes separately so that the raw evidence remains usable.
    state_snapshot = artifacts / 'state-snapshot'
    state_snapshot.mkdir()
    manifest['state_snapshot_files'] = {}
    if state.exists():
        for path in state.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                relative = path.relative_to(state)
                copied = state_snapshot / relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, copied)
                manifest['state_snapshot_files'][relative.as_posix()] = digest(copied)
    manifest['artifacts'] = {
        path.relative_to(artifacts).as_posix(): digest(path)
        for path in [artifacts / 'stdout.jsonl', artifacts / 'stderr.log', artifacts / 'prompt.txt',
                     artifacts / 'assignment.txt',
                     role, home / 'hooks.json'] if path.is_relative_to(artifacts)
    }
    for directory in (runtime, events, rollouts, state_snapshot):
        if directory.exists():
            for path in directory.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:
                    manifest['artifacts'][path.relative_to(artifacts).as_posix()] = digest(path)
    manifest['hooks_config_sha256'] = digest(home / 'hooks.json')
    write_json(artifacts / 'manifest.json', manifest)
    print(artifacts / 'manifest.json')
    return 2  # A raw run never promotes itself, even with exit zero.


if __name__ == '__main__':
    raise SystemExit(main())
