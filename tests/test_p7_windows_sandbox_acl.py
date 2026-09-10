import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from p7_windows_acl import run_directory_acl
from p7_windows_sandbox_acl import inspect_acl, validate_sandbox_acl


class WindowsSandboxAclTests(unittest.TestCase):
    def setUp(self):
        self.root = 'C:/Tmp/Scoped-Root'
        self.sid = 'S-1-5-21-111-222-333-444'
        self.base = {'owner_sid': 'S-1-5-21-10-20-30-1001', 'protected': True,
                     'allowed_sids': ['S-1-5-18', 'S-1-5-32-544', 'S-1-5-21-10-20-30-1001']}
        self.caps = {'workspace': 'S-1-5-21-1-2-3-4', 'readonly': 'S-1-5-21-5-6-7-8',
                     'workspace_by_cwd': {'c:/tmp/scoped-root': self.sid}, 'writable_root_by_path': {}}
        self.actual = {'owner_sid': self.base['owner_sid'], 'protected': True,
                       'rules': [dict(sid=s, mask=0x1f01ff, type=0, inherited=False, inheritance=3, propagation=0)
                                 for s in self.base['allowed_sids']]}
        self.actual['rules'].append(dict(sid=self.sid, mask=0x1301bf, type=0, inherited=False, inheritance=3, propagation=0))

    def test_exact_native_capability_is_bound_to_canonical_workspace(self):
        result = validate_sandbox_acl(self.actual, self.base, self.caps, self.root.replace('/', '\\'))
        self.assertEqual(result['workspace_capability_sid'], self.sid)
        with self.assertRaises(ValueError):
            validate_sandbox_acl(self.actual, self.base, self.caps, 'C:/Tmp/Other-Root')

    def test_foreign_principal_or_expanded_ace_is_rejected(self):
        changes = [lambda a: a['rules'].append(dict(a['rules'][0], sid='S-1-1-0')),
                   lambda a: a['rules'][-1].update(mask=0x1f01ff),
                   lambda a: a['rules'][-1].update(inherited=True),
                   lambda a: a['rules'][-1].update(type=1),
                   lambda a: a.update(protected=False),
                   lambda a: a.update(owner_sid='S-1-5-18')]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                altered = copy.deepcopy(self.actual)
                change(altered)
                with self.assertRaises(ValueError):
                    validate_sandbox_acl(altered, self.base, self.caps, self.root)

    def test_registry_mismatch_or_reused_capability_is_rejected(self):
        changes = [lambda c: c['workspace_by_cwd'].update({'c:/tmp/other': self.sid}),
                   lambda c: c['writable_root_by_path'].update({'c:/tmp/other': self.sid}),
                   lambda c: c.update(readonly=self.sid),
                   lambda c: c.update(readonly=None),
                   lambda c: c['workspace_by_cwd'].update({'c:/tmp/scoped-root': 'S-1-5-21-4294967296-2-3-4'})]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                altered = copy.deepcopy(self.caps)
                change(altered)
                with self.assertRaises(ValueError):
                    validate_sandbox_acl(self.actual, self.base, altered, self.root)

    @unittest.skipUnless(os.name == 'nt', 'Windows-only native DACL contract')
    def test_native_acl_roundtrip_and_write_dac_escalation_rejection(self):
        with tempfile.TemporaryDirectory(prefix='p7-sandbox-acl-') as temporary:
            root = Path(temporary).resolve()
            baseline = run_directory_acl(root, secure=True)
            caps = dict(self.caps, workspace_by_cwd={root.as_posix().lower(): self.sid})
            script = r'''$v=[Console]::In.ReadToEnd() | ConvertFrom-Json
$acl=[IO.Directory]::GetAccessControl($v.path)
$sid=New-Object Security.Principal.SecurityIdentifier($v.sid)
$rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,[Security.AccessControl.FileSystemRights]$v.mask,'ContainerInherit,ObjectInherit','None','Allow')
$acl.SetAccessRule($rule)
[IO.Directory]::SetAccessControl($v.path,$acl)'''
            for mask in (0x1301bf, 0x1f01ff):
                subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                               input=json.dumps({'path': str(root), 'sid': self.sid, 'mask': mask}).encode(),
                               capture_output=True, check=True)
                actual = inspect_acl(root)
                if mask == 0x1301bf:
                    validate_sandbox_acl(actual, baseline, caps, root)
                else:
                    with self.assertRaises(ValueError):
                        validate_sandbox_acl(actual, baseline, caps, root)
