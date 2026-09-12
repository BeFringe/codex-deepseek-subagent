"""Private per-run Windows DACL; inspect mode never changes permissions."""

import base64
import json
import os
from pathlib import Path
import subprocess


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$inputObject = [Console]::In.ReadToEnd() | ConvertFrom-Json
if ($inputObject.mode -notin @('secure','inspect')) { throw 'Invalid ACL operation' }
$path = [IO.Path]::GetFullPath([string]$inputObject.path)
$item = Get-Item -LiteralPath $path
$isFile = $inputObject.kind -eq 'file'
if ($inputObject.kind -notin @('file','directory') -or
    $item.PSIsContainer -eq $isFile -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Expected a regular file or directory of the requested kind'
}
$userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$expected = @($userSid.Value, 'S-1-5-18', 'S-1-5-32-544') | Sort-Object -Unique
if ($inputObject.mode -eq 'secure') {
    if ($isFile) { throw 'File inspection must never modify permissions' }
    if (@(Get-ChildItem -LiteralPath $path -Force).Count -ne 0) { throw 'Secure only a newly empty run root' }
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetOwner($userSid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in $expected) {
        $identity = New-Object Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    [IO.Directory]::SetAccessControl($path, $acl)
}
$actual = if ($isFile) { [IO.File]::GetAccessControl($path) } else { [IO.Directory]::GetAccessControl($path) }
$inheritance = if ($isFile) { 'None' } else { 'ContainerInherit,ObjectInherit' }
$rules = @($actual.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne $expected.Count) { throw 'DACL is not private and exact' }
$actualSids = @($rules | ForEach-Object { $_.IdentityReference.Value } | Sort-Object -Unique)
if (@(Compare-Object $expected $actualSids).Count -ne 0) { throw 'Unexpected ACL principal' }
foreach ($rule in $rules) {
    if ($rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl' -or
        $rule.IsInherited -or $rule.InheritanceFlags -ne $inheritance -or
        $rule.PropagationFlags -ne 'None') { throw 'Unexpected run-root ACL rule' }
}
$owner = $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value
if ($owner -ne $userSid.Value) { throw 'Run root is not owned by this operator' }
@{ schema=1; owner_sid=$owner; protected=$true; allowed_sids=$actualSids;
   sddl=$actual.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access -bor
        [Security.AccessControl.AccessControlSections]::Owner) } | ConvertTo-Json -Compress
'''


def _run_acl(path, *, kind, secure=False):
    if os.name != 'nt':
        raise RuntimeError('native Windows ACL inspection is required')
    powershell = Path(os.environ['SystemRoot']) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    encoded = base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(
        [str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
        input=json.dumps({'path': str(Path(path).resolve(strict=True)),
                          'kind': kind,
                          'mode': 'secure' if secure else 'inspect'}).encode('ascii'),
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        # PowerShell stderr can use CLIXML; do not obscure the fail-closed verdict
        # with an unrelated decoding error or echo host identity unnecessarily.
        raise RuntimeError('Windows run-root ACL qualification failed')
    return json.loads(result.stdout.decode('utf-8-sig'))


def run_directory_acl(path, *, secure=False):
    return _run_acl(path, kind='directory', secure=secure)


def run_file_acl(path):
    return _run_acl(path, kind='file')
