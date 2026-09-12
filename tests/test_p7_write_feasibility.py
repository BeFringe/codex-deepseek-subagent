import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from p7_write_feasibility import derive, collect


class ConcreteFeasibilityTests(unittest.TestCase):
    def test_collection_preserves_actual_crlf_input_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            data = b'authoritative\r\n'
            (root / 'docs/phase1-evidence.md').write_bytes(data)
            baseline = {'root': str(root), 'status': '', 'files': {
                'docs/phase1-evidence.md': hashlib.sha256(data).hexdigest()}}
            packet = collect(root, baseline)
            self.assertEqual(packet['inputs']['authoritative_input_utf8'].encode(), data)
            self.assertEqual(packet['attestation']['owner_decision'], 'dispatch')

    def inputs(self):
        root = str(Path.cwd().resolve())
        return {'baseline': {'root': root, 'status': '', 'files': {
                    'docs/phase1-evidence.md': hashlib.sha256(b'authoritative\n').hexdigest()}},
                'authoritative_input_utf8': 'authoritative\n',
                'patch': f'*** Begin Patch\n*** Add File: {Path(root) / "qualified.txt"}\n+G4_CHILD_WRITE_QUALIFIED\n*** End Patch'}

    def test_changed_inputs_cannot_reuse_prior_derived_receipt(self):
        inputs = self.inputs()
        original = derive(inputs)
        changed = copy.deepcopy(inputs)
        changed['authoritative_input_utf8'] = 'different\n'
        rejected = derive(changed)
        self.assertEqual(original['attestation']['owner_decision'], 'dispatch')
        self.assertEqual(rejected['attestation']['owner_decision'], 'block')
        self.assertNotEqual(original['attestation']['counterexample_probe']['probe_input_sha256'],
                            rejected['attestation']['counterexample_probe']['probe_input_sha256'])

    def test_dirty_or_existing_target_blocks_concrete_addition(self):
        for change in ('dirty', 'existing'):
            with self.subTest(change=change):
                inputs = self.inputs()
                if change == 'dirty':
                    inputs['baseline']['status'] = ' M other.txt'
                else:
                    inputs['baseline']['files']['qualified.txt'] = hashlib.sha256(b'prior').hexdigest()
                self.assertEqual(derive(inputs)['attestation']['owner_decision'], 'block')

    def test_wrong_target_or_content_fails_even_if_one_call(self):
        for old, new in (('qualified.txt', 'foreign.txt'), ('G4_CHILD_WRITE_QUALIFIED', 'OTHER')):
            with self.subTest(change=new):
                inputs = self.inputs()
                inputs['patch'] = inputs['patch'].replace(old, new)
                self.assertEqual(derive(inputs)['attestation']['owner_decision'], 'block')


if __name__ == '__main__':
    unittest.main()
