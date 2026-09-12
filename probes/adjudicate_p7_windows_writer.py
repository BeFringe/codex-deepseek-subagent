"""Consume one fully checked closed writer run; never grant general write permission."""
import argparse
import json
import os
from pathlib import Path

from verify_p7_windows_mutation_outcome import verify, read_json, require, one, digest
from compatibility_state import StateStore, compact_invariant_sha256, provenance_policy_sha256
from runtime_guard import parse_attestation, collect_git_snapshot, validate_complete_write_observation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'owner receipt already exists')
    require(args.output.parent.resolve(strict=True) == args.manifest.parent.resolve(strict=True),
            'owner receipt must stay inside the verified private run directory')
    m = read_json(args.manifest)
    require(m.get('measured_feasibility') is True and m.get('parent_claim_barrier') is True
            and m['mutation_case'] == 'positive', 'complete bounded writer inputs absent')
    outcome = verify(args.manifest)
    store = StateStore(Path(m['state']))
    report = one(list((store.root / 'reported').glob('*.json')), 'writer report')
    envelope = store._validated_envelope(report)
    capsule, binding = envelope['capsule'], envelope['binding']
    final = envelope['final_attestation']
    # Reparse the schema and independently recompute identity, disk, provenance,
    # verification and trusted writer observation before touching authority.
    parsed = parse_attestation('BEGIN CODEX WORKER ATTESTATION\n' + json.dumps(final) + '\nEND CODEX WORKER ATTESTATION')
    current = collect_git_snapshot(capsule['root']['path'])
    expected = {'assignment_id': capsule['assignment_id'], 'handoff_id': capsule['handoff_id'],
                'capsule_sha256': capsule['capsule_sha256'],
                'compact_invariant_sha256': compact_invariant_sha256(capsule),
                'canonical_agent_path': binding['canonical_agent_path'],
                'recovery_count': envelope['runtime']['recovery_count'], **current,
                'context_lost': False, 'authority_violation': False, 'assigned_slice_complete': True,
                'inventory_summaries': [],
                'verification': [{'command': c, 'exit_code': 0} for c in capsule['verification']]}
    require(all(parsed[k] == v for k, v in expected.items()), 'fresh writer attestation mismatch')
    require(parsed['authority_provenance']['policy_sha256'] == provenance_policy_sha256(capsule)
            and parsed['authority_provenance']['worker_claimed_origin'] == 'owner_internal'
            and parsed['authority_provenance']['test_only_injection_used'] is False
            and envelope['runtime']['first_git_attested_at'] is not None, 'writer provenance not independently admissible')
    validate_complete_write_observation(store, binding, capsule, parsed, current)
    require(not list((store.root / 'writer_claim').glob('*.json'))
            and not list((store.root / 'active').glob('*.json'))
            and not list((store.root / 'pending').glob('*.json'))
            and not list((store.root / 'claimed').glob('*.json')), 'in-flight authority remains')
    adjudication = {key: 'pass' for key in ('location_integrity', 'mutation_scope_integrity',
        'verification_freshness', 'derivation_provenance_integrity', 'feasibility_contract_integrity')}
    adjudication['evidence_sha256'] = digest(args.manifest)
    consumed = store.adjudicate_parent(capsule['assignment_id'], adjudication)
    require(consumed == store.path('consumed', capsule['assignment_id']) and consumed.is_file()
            and not report.exists(), 'authority consumption failed')
    result = {'schema': 1, 'classification': 'fresh_owner_exact_closed_windows_writer',
              'fresh_adjudicator_pid': os.getpid(), 'manifest_sha256': digest(args.manifest),
              'assignment_id': capsule['assignment_id'], 'consumed_sha256': digest(consumed),
              'adjudication': adjudication, 'outcome': outcome, 'authority_consumed': True,
              'exact_closed_writer_run_qualified': True,
              'scope': 'one native parent, one child, one owned addition, one durable parent denial, then closed',
              'native_sibling_live_qualified': False, 'direct_write_qualified': False,
              'phase1_complete': False, 'p7_complete': False,
              'historical_concurrency_negatives_explained': False,
              'global_process_tree_qualified': False, 'phase2_state': 'closed', 'phase3_state': 'closed'}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'authority_consumed': True, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
