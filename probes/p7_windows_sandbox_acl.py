"""Inspect the exact path-scoped ACE installed by the native Windows sandbox.

This does not change an ACL or accept arbitrary additional principals. cap_sid is
the sandbox's non-secret SID registry; auth.json is never inspected here.
"""
import base64
import json
import os
from pathlib import Path
import re
import string
import subprocess


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$inputObject = [Console]::In.ReadToEnd() | ConvertFrom-Json
$path = [IO.Path]::GetFullPath([string]$inputObject.path)
$item = Get-Item -LiteralPath $path
if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Expected a regular directory'
}
$acl = [IO.Directory]::GetAccessControl($path)
$rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]) | ForEach-Object {
    @{ sid=$_.IdentityReference.Value; mask=[int]$_.FileSystemRights;
       type=[int]$_.AccessControlType; inherited=$_.IsInherited;
       inheritance=[int]$_.InheritanceFlags; propagation=[int]$_.PropagationFlags }
})
@{ owner_sid=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
   protected=$acl.AreAccessRulesProtected; rules=$rules;
   sddl=$acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access -bor
        [Security.AccessControl.AccessControlSections]::Owner) } | ConvertTo-Json -Compress -Depth 4
'''


def inspect_acl(path):
    if os.name != 'nt':
        raise RuntimeError('native Windows ACL inspection required')
    executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run(
        [str(executable), '-NoProfile', '-NonInteractive', '-EncodedCommand',
         base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')],
        input=json.dumps({'path': str(Path(path).resolve(strict=True))}).encode('ascii'),
        capture_output=True, timeout=30, check=True,
    )
    return json.loads(result.stdout.decode('utf-8-sig'))


def validate_sandbox_acl(actual, baseline, caps, root):
    # Exact equivalents of canonical_path_key and WRITE_ALLOW_MASK in the pinned
    # Windows sandbox source. The latter excludes WRITE_DAC and WRITE_OWNER.
    key = str(root).replace('\\', '/').translate(str.maketrans(string.ascii_uppercase, string.ascii_lowercase))
    if not isinstance(caps, dict) or set(caps) != {'workspace', 'readonly', 'workspace_by_cwd', 'writable_root_by_path'}:
        raise ValueError('unexpected native capability registry schema')
    if not isinstance(caps['workspace_by_cwd'], dict) or set(caps['workspace_by_cwd']) != {key}:
        raise ValueError('capability registry is not bound to the exact run root')
    sid = caps['workspace_by_cwd'][key]
    if not isinstance(caps['writable_root_by_path'], dict):
        raise ValueError('invalid write-root capability registry')
    others = [caps['workspace'], caps['readonly'], *caps['writable_root_by_path'].values()]
    for value in [sid, *others]:
        if not isinstance(value, str) or re.fullmatch(r'S-1-5-21-(?:[0-9]+-){3}[0-9]+', value) is None:
            raise ValueError('invalid native capability SID')
        if any(int(part) > 0xffffffff for part in value.split('-')[4:]):
            raise ValueError('invalid SID component')
    if sid in others:
        raise ValueError('workspace SID was reused by another capability')
    base_sids = {baseline['owner_sid'], 'S-1-5-18', 'S-1-5-32-544'}
    if set(baseline['allowed_sids']) != base_sids or baseline['protected'] is not True or sid in base_sids:
        raise ValueError('invalid private baseline')
    if actual['owner_sid'] != baseline['owner_sid'] or actual['protected'] is not True:
        raise ValueError('owner or DACL protection changed')
    expected = [dict(sid=s, mask=0x1f01ff, type=0, inherited=False, inheritance=3, propagation=0)
                for s in base_sids]
    expected.append(dict(sid=sid, mask=0x1301bf, type=0, inherited=False, inheritance=3, propagation=0))
    if sorted(actual['rules'], key=lambda item: item['sid']) != sorted(expected, key=lambda item: item['sid']):
        raise ValueError('ACL differs from private baseline plus exact native capability ACE')
    return {'workspace_capability_sid': sid, 'capability_mask': 0x1301bf,
            'scope': 'exact native workspace capability, no additional ACL principals'}
