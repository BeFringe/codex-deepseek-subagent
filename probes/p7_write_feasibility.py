"""Reproducible pre-dispatch feasibility for one concrete addition.

This proves representation/cardinality, not provider reliability or general
writer safety. Inputs and derivation evidence are retained, never dummy hashes.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hooks'))
from feasibility_guard import build_parent_feasibility_attestation
from writer_lease_guard import extract_apply_patch_paths


def derive(inputs):
    patch = inputs['patch']
    paths = extract_apply_patch_paths(patch)
    target = str(Path(inputs['baseline']['root']) / 'qualified.txt')
    checks = {'exact_target': paths == [target], 'clean_baseline': inputs['baseline']['status'] == '',
              'target_absent': 'qualified.txt' not in inputs['baseline']['files'],
              'exact_bytes': patch == f'*** Begin Patch\n*** Add File: {target}\n+G4_CHILD_WRITE_QUALIFIED\n*** End Patch',
              'authoritative_input_bound': hashlib.sha256(inputs['authoritative_input_utf8'].encode()).hexdigest()
                  == inputs['baseline']['files']['docs/phase1-evidence.md']}
    probe_evidence = {'parsed_paths': paths, 'checks': checks}
    scale_evidence = {'domain': [target], 'operations': [{'kind': 'Add', 'path': target}],
                      'distinct_paths': len(set(paths)), 'compression_applied': False}
    bounded_evidence = {'patch_utf8_bytes': len(patch.encode()), 'required_calls': 1,
                        'derivation': 'one exact freeform patch contains the sole Add operation; no fanout or batching assumption'}
    attestation = build_parent_feasibility_attestation(
        parent_owner_id='phase1.parent',
        exact_claimed_invariant='the concrete absent-target addition has an exact one-call apply_patch representation',
        probe_id='exact-addition-input-counterexample', probe_input=inputs,
        completion_condition='one exact owned-path apply_patch',
        work_budget={'unit': 'tool-call', 'cardinality_domain': 'owned-path', 'limit': 1},
        proposed_mechanism='one concrete Add operation, exact Hook ceiling and writer lease',
        unresolved_assumptions=[],
        run_counterexample_probe=lambda value: {'counterexample_found': not all(checks.values()), 'evidence': probe_evidence},
        assess_bounded_completion=lambda mechanism, budget: {
            'mechanism_measurement': {'unit': 'tool-call', 'cardinality_domain': 'owned-path', 'required_lower_bound': len(set(paths))},
            'scale_evidence': {'basis': 'adversarial_scale_witness', 'witness_input': inputs,
                               'evidence': scale_evidence}, 'evidence': bounded_evidence},
        derive_equivalence_compression=lambda value, mechanism: None)
    return {'schema': 1, 'inputs': inputs, 'probe_evidence': probe_evidence,
            'scale_evidence': scale_evidence, 'bounded_evidence': bounded_evidence,
            'attestation': attestation,
            'limits': ['single concrete input only', 'does not prove provider completion, exclusion, or global process quiescence']}


def collect(root, baseline):
    inputs = {'baseline': baseline,
              'authoritative_input_utf8': (root / 'docs/phase1-evidence.md').read_bytes().decode('utf-8'),
              'patch': f'*** Begin Patch\n*** Add File: {root / "qualified.txt"}\n+G4_CHILD_WRITE_QUALIFIED\n*** End Patch'}
    result = derive(inputs)
    if result['attestation']['owner_decision'] != 'dispatch':
        raise ValueError('concrete addition feasibility rejected')
    return result


def replace_prompt(prompt, packet):
    begin, end = 'BEGIN CODEX WORKER AUTHORITY\n', '\nEND CODEX WORKER AUTHORITY'
    prefix, tail = prompt.split(begin, 1)
    raw, suffix = tail.split(end, 1)
    authority = json.loads(raw)
    authority['execution_contract']['capsule_feasibility_attestation'] = packet['attestation']
    return prefix + begin + json.dumps(authority, separators=(',', ':'), sort_keys=True) + end + suffix
