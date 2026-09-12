"""Windows-native counterpart of the pinned POSIX qualification launchers.

Only constructs an exact headless candidate invocation after validating its
digest, caller posture and per-probe ceiling. No shell emulation is required.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


class LauncherError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LauncherError(message)


def pinned_file(raw, expected, label):
    path = Path(raw)
    require(path.is_absolute(), f"{label} path must be absolute")
    require(path.is_file() and not path.is_symlink(), f"{label} is unavailable")
    require(not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400,
            f"{label} must not be a reparse point")
    require(re.fullmatch('[0-9a-f]{64}', expected), f"{label} digest is invalid")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            f"{label} digest mismatch")
    return path


def temporary_namespace(raw, prefix, label):
    path = Path(raw)
    require(path.is_absolute() and path.resolve() == path and path.is_dir()
            and path.parent == Path(tempfile.gettempdir()).resolve()
            and path.name.startswith(prefix)
            and not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400,
            f"{label} root is outside the fixed temporary namespace")


def git(root, *args):
    result = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True)
    require(result.returncode == 0, 'probe root is not a Git worktree')
    return result.stdout.rstrip('\r\n')


def parse(arguments):
    mode = None
    cd = ''
    take_cd = False
    flags = set()
    for value in arguments:
        if take_cd:
            cd, take_cd = value, False
            continue
        require(value not in ('app-server', 'app', 'remote-control', 'mcp-server'),
                'GUI and server entry points are forbidden')
        if value in ('exec', 'login'):
            require(mode is None, 'multiple candidate entry points are forbidden')
            mode = value
        elif value in ('-C', '--cd'):
            take_cd = True
        elif value.startswith('--cd='):
            cd = value[5:]
        elif (value in ('-c', '--config') or value.startswith('--config=')
              or (value.startswith('-c') and len(value) > 2)):
            raise LauncherError('caller may not override candidate configuration')
        elif (value.split('=')[0] in ('--dangerously-bypass-approvals-and-sandbox',
              '--approve-for-me', '--add-dir', '-s', '--sandbox', '-a', '--ask-for-approval')):
            raise LauncherError('caller may not widen the probe permission posture')
        flags.add(value)
    require(not take_cd, 'working-directory argument is missing')
    return mode, cd, flags


def build(profile, arguments, env):
    def setting(suffix):
        return env.get('CODEX_G4_' + suffix, '')

    def guard(suffix, expected, label):
        value = setting(suffix)
        require(not value or value == expected, f'{label} authorization guard is invalid')
        return bool(value)

    if profile == 'deepseek':
        require(env.get('CODEX_P7_DEEPSEEK_REGRESSION_AUTHORIZED') == 'schema1-native-readonly',
                'probe authorization guard is absent')
    else:
        require(setting('LIVE_SELECTION_AUTHORIZED') == 'schema2-paired-probe', 'live selection guard is absent')
    if profile == 'handover':
        require(setting('P5B_HANDOVER_PROBE_AUTHORIZED') == 'schema1-exact-barrier-replacement',
                'handover probe guard is absent')
        require(arguments and arguments[0] == 'exec', 'only headless exec is allowed')
    candidate = pinned_file(setting('CANDIDATE_BIN'), setting('CANDIDATE_SHA256'), 'candidate')
    mode, cd, flags = parse(arguments)
    ephemeral = '--ephemeral' in flags
    stateful_root = setting('SESSIONMETA_PROBE_ROOT')
    sandbox, code_mode, catalog, extra = 'read-only', False, '', []
    if mode == 'login':
        require(profile == 'plaintext' and arguments == ['login', 'status'], 'only login status is allowed')
    else:
        require(mode == 'exec', 'only headless exec or login status is allowed')
        for flag in ('--ignore-user-config', '--ignore-rules'):
            require(flag in flags, f'exec requires {flag}')
        if profile == 'deepseek':
            stateful_root = env.get('CODEX_P7_DEEPSEEK_PROBE_ROOT', '')
            require(not ephemeral, 'probe must retain SessionMeta')
            temporary_namespace(stateful_root, 'codex-p7-deepseek-regression.', 'probe')
            temporary_namespace(env.get('CODEX_DEEPSEEK_HANDOFF_DIR', ''), 'codex-p7-deepseek-handoff.', 'handoff')
            require('DEEPSEEK_API_KEY' in env, 'DeepSeek credential is absent')
            role = pinned_file(env.get('CODEX_P7_DEEPSEEK_ROLE_CONFIG', ''),
                               env.get('CODEX_P7_DEEPSEEK_ROLE_SHA256', ''), 'role config')
            require(role.name == 'v4-flash-worker.toml' and role.parent.name == 'agents',
                    'role config must be the exact generic v4 role path')
            extra = ['features.multi_agent_v2.child_model_providers={v4_flash_worker="deepseek"}',
                     'agents.v4_flash_worker.config_file=' + json.dumps(str(role)),
                     'model_providers.deepseek.name="DeepSeek P7 child"',
                     'model_providers.deepseek.base_url="https://api.deepseek.com"',
                     'model_providers.deepseek.env_key="DEEPSEEK_API_KEY"',
                     'model_providers.deepseek.wire_api="responses"',
                     'model_providers.deepseek.requires_openai_auth=false',
                     'model_providers.deepseek.request_max_retries=0',
                     'model_providers.deepseek.stream_max_retries=0']
        if not ephemeral:
            if profile != 'deepseek':
                require(setting('SESSIONMETA_PROBE_AUTHORIZED') == 'schema1-headless-stateful',
                        'stateful exec requires the SessionMeta probe guard')
            require(Path(stateful_root).is_absolute(), 'stateful probe root must be absolute')
            require(cd == stateful_root, 'stateful exec requires the exact guarded root')
            require('--json' in flags, 'stateful exec requires JSON event output')
            require('--dangerously-bypass-hook-trust' in flags, 'stateful exec requires the vetted Hook trust bypass')
            require(Path(git(cd, 'rev-parse', '--show-toplevel')) == Path(cd),
                    'stateful probe root is not the exact Git top level')
            frontier = git(cd, 'status', '--short', '--untracked-files=all')
            if profile == 'handover':
                require(setting('P5B_HANDOVER_PROBE_AUTHORIZED') == 'schema1-exact-barrier-replacement',
                        'handover probe guard is absent')
                require(setting('P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED') == 'schema1-exact-write-then-close',
                        'P5b write-then-close guard is absent')
                temporary_namespace(cd, 'codex-g4-p5b-write-termination.', 'handover')
                require(frontier == '?? qualified.txt', 'handover root is not the exact prior dirty frontier')
                pinned_file(str(Path(cd) / 'qualified.txt'),
                            '4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c', 'handover target frozen prior bytes')
                sandbox, catalog = 'workspace-write', 'stderr-v2-parent-child-closed'
            else:
                require(not frontier, 'stateful probe root is not clean')
            if profile == 'deepseek':
                require(git(cd, 'symbolic-ref', '--short', 'HEAD'), 'probe root must have an attached branch')
        if profile == 'handover':
            require(not ephemeral, 'handover probe must retain SessionMeta')
        if profile == 'plaintext':
            write = guard('EXACT_WRITE_PROBE_AUTHORIZED', 'schema1-exact-temporary-git-root', 'write probe')
            if write:
                require(not ephemeral, 'write probe must retain SessionMeta')
                temporary_namespace(cd, 'codex-g4-write-', 'write probe')
                sandbox = 'workspace-write'
            if guard('AUTO_COMPACT_PROBE_AUTHORIZED', 'schema1-post-action-20000', 'auto-compact probe'):
                require(not ephemeral, 'auto-compact probe must retain SessionMeta')
                extra = ['model_auto_compact_token_limit=20000']
            if guard('FAILED_PATCH_CALLBACK_PROBE_AUTHORIZED', 'schema1-root-failed-apply-patch', 'failed-patch callback probe'):
                require(write, 'failed-patch callback probe requires the exact write guard')
                temporary_namespace(cd, 'codex-g4-write-posttool-', 'failed-patch callback')
                code_mode = True
            conflict = guard('PARENT_CHILD_WRITER_CONFLICT_PROBE_AUTHORIZED', 'schema1-exact-active-child-claim', 'parent/child writer conflict probe')
            if conflict:
                require(write, 'parent/child writer conflict probe requires the exact write guard')
                temporary_namespace(cd, 'codex-g4-write-parent-conflict.', 'parent/child writer conflict')
                code_mode, catalog = True, 'stderr-v2-parent-child-closed'
            sibling = guard('SIBLING_SPAWN_ADMISSION_PROBE_AUTHORIZED', 'schema1-exact-g4-only', 'sibling admission probe')
            termination = setting('P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED')
            pretool = setting('REQUIRED_PRETOOL_PROBE_AUTHORIZED')
            if sibling:
                require(not ephemeral, 'sibling admission probe must retain SessionMeta')
                require(not (write or conflict or termination or pretool), 'sibling admission probe cannot combine with another probe')
                temporary_namespace(cd, 'codex-g4-sibling-admission.', 'sibling admission probe')
                catalog = 'stderr-v2-parent-child-closed'
            if termination:
                require(not ephemeral, 'P5b termination probe must retain SessionMeta')
                prefixes = {'schema1-exact-idle-child': 'codex-g4-p5b-termination.',
                            'schema1-exact-tracked-process': 'codex-g4-p5b-tracked-process.',
                            'schema1-exact-write-then-close': 'codex-g4-p5b-write-termination.'}
                require(termination in prefixes, 'P5b termination probe authorization guard is invalid')
                temporary_namespace(cd, prefixes[termination], 'P5b termination probe')
                catalog = 'stderr-v2-parent-child-closed'
                if termination == 'schema1-exact-write-then-close':
                    sandbox = 'workspace-write'
                if termination == 'schema1-exact-tracked-process':
                    host = candidate.with_name('codex-code-mode-host.exe')
                    pinned_file(str(host), setting('CODE_MODE_HOST_SHA256'), 'P5b code-mode host')
                    code_mode = True
            if pretool:
                require(not ephemeral, 'required PreToolUse probe must retain SessionMeta')
                require(not (write or conflict or termination), 'required PreToolUse probe cannot combine with another probe')
                temporary_namespace(cd, 'codex-g4-required-pretool.', 'required PreToolUse probe')
                catalog = 'stderr-v2-parent-child-closed'
                configurations = {'schema1-exact-missing-handler-parent': 'features.hooks=false',
                                  'schema1-exact-failed-handler-child': 'hooks.PreToolUse=[{matcher="^apply_patch$",hooks=[{type="command",command="cmd.exe /d /c exit 1",timeout=5}]}]'}
                require(pretool in configurations, 'required PreToolUse probe authorization guard is invalid')
                if not extra:
                    extra = [configurations[pretool]]
    environment = dict(env)
    environment.pop('CODEX_G4_TOOL_CATALOG_RECEIPT', None)
    if catalog:
        environment['CODEX_G4_TOOL_CATALOG_RECEIPT'] = catalog
    configurations = ['features.multi_agent_v2.enabled=true',
                      'features.multi_agent_v2.message_delivery="plaintext"',
                      'features.multi_agent_v2.tool_namespace="g4_assignment"']
    if profile == 'deepseek':
        configurations += extra + ['features.code_mode_host=false']
    else:
        configurations += ['features.code_mode_host=' + str(code_mode).lower()] + extra
    command = ([sys.executable, str(candidate)] if candidate.suffix == '.py' else [str(candidate)])
    for configuration in configurations:
        command += ['-c', configuration]
    command += ['-a', 'never', '-s', sandbox, *arguments]
    return command, environment


def main():
    try:
        require(os.name == 'nt', 'this launcher requires Windows')
        require(len(sys.argv) > 2 and sys.argv[1] in ('plaintext', 'handover', 'deepseek'), 'unknown qualification profile')
        command, environment = build(sys.argv[1], sys.argv[2:], os.environ)
        return subprocess.call(command, env=environment)
    except (LauncherError, OSError) as error:
        print('codex Windows candidate launcher: ' + str(error), file=sys.stderr)
        return 78


if __name__ == '__main__':
    raise SystemExit(main())
