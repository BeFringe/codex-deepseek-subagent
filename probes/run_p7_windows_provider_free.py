"""Run the complete suite and retain per-test outcomes without platform waivers."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'probes' / 'p7-windows-provider-free-20260911.json'
RENAMED_EQUIVALENCE_CASES = {
    'test_plaintext_pair_probe_guard.PlaintextPairProbeGuardTests.test_state_directory_must_be_canonical_private_tmp_descendant':
        'test_plaintext_pair_probe_guard.PlaintextPairProbeGuardTests.test_state_directory_must_be_canonical_temporary_root_descendant',
}


def equivalence_cases(baseline, cases, *, platform):
    actual = {case['test_id']: case for case in cases}
    result = []
    for previous in baseline['cases']:
        if (previous.get('classification') or {}).get('category') != 'b':
            continue
        test_id = previous['test_id']
        executed_id = RENAMED_EQUIVALENCE_CASES.get(test_id, test_id)
        case = actual.get(executed_id)
        module = test_id.split('.')[0]
        backend = ('windows_powershell_handoff' if module == 'test_plaintext_handoff' else
                   'windows_native_launcher' if module in
                   ('test_plaintext_candidate_wrapper', 'test_deepseek_regression_candidate_wrapper') else
                   'same_platform_independent_contract')
        sources = ['tests/' + module + '.py']
        if backend == 'windows_powershell_handoff':
            sources += ['hooks/plaintext-handoff.ps1', 'tests/private_output_assertions.py',
                        'probes/p7_windows_acl.py']
        elif backend == 'windows_native_launcher':
            sources += ['probes/windows_candidate_launcher.py', 'tests/windows_launcher_fixture.py']
        result.append({'baseline_test_id': test_id, 'executed_test_id': executed_id,
                       'backend': backend, 'source_paths': sources,
                       'actual_status': case['status'] if case else 'missing',
                       'windows_equivalence_proven': platform == 'win32' and case is not None
                           and case['status'] == 'passed' and not case['events']})
    return result


def classify(test_id, diagnostic, status):
    if status == 'passed':
        return None
    if 'originating-host' in diagnostic:
        return {'category': 'c', 'reason': 'Originating-host raw anchor unavailable',
                'windows_equivalence_proven': False}
    if 'test_plaintext_handoff.' in test_id:
        return {'category': 'b', 'reason': 'Python handoff explicitly requires POSIX locking; native PowerShell has a separate suite',
                'windows_equivalence_proven': False}
    if 'WinError 193' in diagnostic or 'test_plaintext_candidate_wrapper.' in test_id:
        return {'category': 'b', 'reason': 'POSIX shell executable/launcher premise; Windows equivalent not established by this test',
                'windows_equivalence_proven': False}
    if '/private/tmp' in diagnostic or 'sandbox probe parent is unavailable' in diagnostic:
        return {'category': 'b', 'reason': 'POSIX temporary-root fixture or authority ceiling; not waived as Windows coverage',
                'windows_equivalence_proven': False}
    if 'test_evidence_binding.' in test_id:
        return {'category': 'd', 'reason': 'Windows no-follow handle walk / terminal identity proof remains unresolved',
                'windows_equivalence_proven': False}
    if 'WinError 1314' in diagnostic:
        return {'category': 'd', 'reason': 'Symlink creation privilege unavailable; no equivalent reparse-point adversarial proof yet',
                'windows_equivalence_proven': False}
    if '438 != 384' in diagnostic:
        return {'category': 'd', 'reason': 'POSIX chmod 0600 does not prove a private Windows DACL for this builder',
                'windows_equivalence_proven': False}
    if 'root is not canonical and absolute' in diagnostic and 'test_g4_parent_non_git_writer_live.' in test_id:
        return {'category': 'c', 'reason': 'Frozen macOS writer receipt requires originating-host canonical filesystem validation',
                'windows_equivalence_proven': False}
    return {'category': 'd', 'reason': 'Unresolved failure; manual review required, no automatic platform exclusion',
            'windows_equivalence_proven': False}


class AuditResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = {}

    def startTest(self, test):
        self.cases[test.id()] = {'test_id': test.id(), 'status': 'passed', 'events': []}
        super().startTest(test)

    def record(self, test, status, diagnostic):
        case = self.cases.setdefault(test.id(), {'test_id': test.id(), 'events': []})
        case['status'] = status
        case['events'].append({'status': status, 'diagnostic': diagnostic})

    def addFailure(self, test, err):
        self.record(test, 'failed', self._exc_info_to_string(err, test))
        super().addFailure(test, err)

    def addError(self, test, err):
        self.record(test, 'error', self._exc_info_to_string(err, test))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.record(test, 'skipped', reason)
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            status = 'failed' if issubclass(err[0], test.failureException) else 'error'
            self.record(test, status, str(subtest) + '\n' + self._exc_info_to_string(err, test))
        super().addSubTest(test, subtest, err)

    def addExpectedFailure(self, test, err):
        self.record(test, 'expected_failure', self._exc_info_to_string(err, test))
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.record(test, 'unexpected_success', 'Unexpected success requires review')
        super().addUnexpectedSuccess(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; preserve the prior audit')
    os.chdir(ROOT)
    sys.dont_write_bytecode = True
    tested_sources = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for folder in ('tests', 'hooks', 'probes')
                      for p in (ROOT / folder).glob('*.py')}
    tested_backends = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for folder in ('tests', 'hooks', 'probes')
                       for suffix in ('*.ps1', '*.sh') for p in (ROOT / folder).glob(suffix)}
    baseline_bytes = BASELINE.read_bytes()
    baseline = json.loads(baseline_bytes)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=AuditResult).run(suite)
    cases = list(result.cases.values())
    for case in cases:
        diagnostic = '\n'.join(event['diagnostic'] for event in case['events'])
        case['classification'] = classify(case['test_id'], diagnostic, case['status'])
    equivalence = equivalence_cases(baseline, cases, platform=sys.platform)
    equivalence_complete = len(equivalence) == 85 and all(
        case['windows_equivalence_proven'] for case in equivalence)
    unresolved = [case for case in cases if case['status'] != 'passed' and
                  (case['classification'] or {}).get('category') != 'c']
    report = {
        'schema': 1, 'host_platform': sys.platform,
        'checkout_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'tested_source_sha256': tested_sources,
        'tested_backend_sha256': tested_backends,
        'equivalence_baseline_path': BASELINE.relative_to(ROOT).as_posix(),
        'equivalence_baseline_sha256': hashlib.sha256(baseline_bytes).hexdigest(),
        'windows_equivalence_cases': equivalence,
        'windows_equivalence_counts': dict(Counter(
            'proven' if case['windows_equivalence_proven'] else 'unproven' for case in equivalence)),
        'windows_relevant_executable_suite_passed': sys.platform == 'win32'
            and equivalence_complete and not unresolved,
        'tests_run': result.testsRun,
        'test_outcome_counts': dict(Counter(case['status'] for case in cases)),
        'unittest_event_counts': {'failures': len(result.failures), 'errors': len(result.errors),
                                 'skips': len(result.skipped)},
        'classification_is_not_a_skip_or_waiver': True,
        'suite_passed': result.wasSuccessful(),
        'windows_live_qualified': False, 'phase1_complete': False,
        'direct_write_qualified': False, 'cases': cases,
    }
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
