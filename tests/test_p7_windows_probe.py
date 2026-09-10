"""Provider-free safety checks for the Windows raw-evidence collector."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
from run_p7_windows_live import invocation, snapshot
from adjudicate_p7_windows_live import AdjudicationError, verify_close, verify_catalog
from p7_windows_acl import run_directory_acl


class WindowsProbeTests(unittest.TestCase):
    def test_read_only_catalog_rejects_child_mutation_and_process_tools(self):
        parent = ['apply_patch', 'view_image'] + ['g4_assignment.' + name for name in
            ('spawn_agent', 'send_message', 'followup_task', 'close_agent',
             'interrupt_agent', 'list_agents', 'wait_agent')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stderr.log'
            for provider in ('deepseek', 'zhipu'):
                tool_name = 'list_agents' if provider == 'deepseek' else 'g4_assignment.list_agents'
                for extra in (None, 'apply_patch', 'exec_command', 'g4_assignment.spawn_agent'):
                    rows = []
                    child = ['view_image', tool_name] + ([extra] if extra else [])
                    for actor, names in [('qualification_parent', parent), ('qualification_child', child)]:
                        registered = []
                        for name in names:
                            namespace, _, short = name.rpartition('.')
                            registered.append({'name': short, 'namespace': namespace or None})
                        rows.append({'actor_kind': actor, 'catalog': {
                            'registered_tools': registered, 'code_mode_tool_names': {},
                            'can_manage_children': actor == 'qualification_parent'}})
                    path.write_text(''.join('G4_TOOL_CATALOG_RECEIPT_V2 ' + json.dumps(row) + '\n'
                                            for row in rows), encoding='utf-8')
                    if extra:
                        with self.assertRaises(AdjudicationError):
                            verify_catalog(path, provider)
                    else:
                        verify_catalog(path, provider)
                        other = 'zhipu' if provider == 'deepseek' else 'deepseek'
                        with self.assertRaises(AdjudicationError):
                            verify_catalog(path, other)

    def test_snapshot_observes_index_and_worktree_without_writing_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True)
            git('init', '-b', 'main')
            (root / 'fixture.txt').write_text('before\n', encoding='utf-8')
            git('add', 'fixture.txt')
            git('-c', 'user.name=test', '-c', 'user.email=test@invalid',
                'commit', '-m', 'fixture')
            # Stage a change without writing a tree object. A read-only observer
            # must not synthesize that missing tree while inspecting the index.
            (root / 'fixture.txt').write_text('staged\n', encoding='utf-8')
            git('add', 'fixture.txt')
            objects = {p.relative_to(root): p.read_bytes()
                       for p in (root / '.git' / 'objects').rglob('*') if p.is_file()}
            index_before = (root / '.git' / 'index').read_bytes()
            first = snapshot(root)
            self.assertEqual(index_before, (root / '.git' / 'index').read_bytes())
            self.assertEqual(objects, {p.relative_to(root): p.read_bytes()
                             for p in (root / '.git' / 'objects').rglob('*') if p.is_file()})
            (root / 'fixture.txt').write_text('unstaged\n', encoding='utf-8')
            second = snapshot(root)
            self.assertEqual(first['index_sha256'], second['index_sha256'])
            self.assertNotEqual(first['files'], second['files'])

    def test_provider_selection_keeps_parent_and_permissions_pinned(self):
        for provider in ('deepseek', 'zhipu'):
            args = invocation(Path('candidate.exe'), Path('worktree'), Path('role.toml'), provider)
            self.assertIn('model_provider="openai"', args)
            self.assertIn('forced_login_method="chatgpt"', args)
            self.assertIn('features.multi_agent_v2.child_model_providers.'
                          'g4_qualification_probe_worker=' + json.dumps(provider), args)
            self.assertEqual(args[args.index('-s') + 1], 'read-only')
            self.assertEqual(args[args.index('-a') + 1], 'never')
            self.assertIn('model_providers.' + provider + '.wire_api="responses"', args)
            if provider == 'deepseek':
                self.assertIn('model_providers.deepseek.supports_namespace_tools=false', args)
                self.assertIn('model_providers.deepseek.requires_function_call_output_adjacency=true', args)

    def observer(self, raw, guard_source):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guard = root / 'guard.py'
            guard.write_text(guard_source, encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(ROOT / 'probes' / 'p7_windows_hook.py'),
                 '--guard', str(guard), '--state', str(root / 'state'),
                 '--events', str(root)], input=raw, capture_output=True, timeout=30)
            records = list(root.glob('*.json'))
            self.assertEqual(len(records), 1)
            return result, json.loads(records[0].read_text(encoding='utf-8'))

    def test_observer_preserves_utf8_input_and_denial_output(self):
        raw = '{ "hook_event_name": "PreToolUse", "message": "中文\\n赋值" }'.encode()
        source = ('import sys\n'
                  'sys.stdin.buffer.read()\n'
                  'sys.stdout.buffer.write(b\'{"permissionDecision":"deny"}\')\n'
                  'sys.exit(2)\n')
        result, record = self.observer(raw, source)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(record['stdin_utf8'].encode(), raw)
        self.assertEqual(record['stdin_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(record['stdout'].encode(), result.stdout)
        self.assertEqual(record['exit_code'], 2)

    def test_malformed_input_never_dispatches_guard_and_retains_failure(self):
        result, record = self.observer(b'[]', 'raise AssertionError("must not dispatch")\n')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(record['observer_error'], 'ValueError')
        self.assertNotIn('stdout', record)

    def test_close_requires_each_barrier_and_exact_process_actor_set(self):
        close = {'target_thread_id': 'child', 'target_agent_path': '/root/child',
                 'session_loop_terminated': True, 'model_callable_process_bootstrap_absent': True,
                 'tracked_process_termination_confirmed': True,
                 'closed_catalog_actor_quiescence_claimed': True,
                 'tracked_background_processes_before_close': 0,
                 'process_tree_quiescence_claimed': False}
        maps = ('tracked_process_ids_by_thread', 'confirmed_exit_process_ids_by_thread',
                'unconfirmed_exit_process_ids_by_thread', 'unresolved_start_process_ids_by_thread')
        close.update({key: {'child': []} for key in maps})
        verify_close(close, 'child', '/root/child')
        for key in close:
            broken = {name: value for name, value in close.items() if name != key}
            with self.subTest(missing=key), self.assertRaises(AdjudicationError):
                verify_close(broken, 'child', '/root/child')
        for key in maps:
            for value in ({}, {'child': [123]}, {'child': [], 'unknown': []}):
                with self.subTest(field=key, value=value), self.assertRaises(AdjudicationError):
                    verify_close(dict(close, **{key: value}), 'child', '/root/child')

    @unittest.skipUnless(os.name == 'nt', 'requires native Windows DACLs')
    def test_private_acl_survives_inspection_and_rejects_added_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'evidence 中文 directory'
            root.mkdir()
            secured = run_directory_acl(root, secure=True)
            self.assertTrue(secured['protected'])
            self.assertEqual(run_directory_acl(root), secured)
            (root / 'fixture.txt').write_text('evidence', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                run_directory_acl(root, secure=True)  # Never reset a populated root.
            self.assertEqual(run_directory_acl(root), secured)
            icacls = Path(os.environ['SystemRoot']) / 'System32' / 'icacls.exe'
            subprocess.run([str(icacls), str(root), '/grant', '*S-1-5-11:(OI)(CI)M'],
                           check=True, capture_output=True, timeout=15)
            with self.assertRaises(RuntimeError):
                run_directory_acl(root)


if __name__ == '__main__':
    unittest.main()
