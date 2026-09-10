import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'probes'))
from p7_windows_model_catalog import build, descriptor, validate_generated


class WindowsModelCatalogTests(unittest.TestCase):
    def test_wrong_slug_hash_missing_parent_and_duplicate_fail_closed(self):
        raw = json.dumps({'models': [{'slug': 'parent', 'marker': 'preserved'}]}).encode()
        digest = hashlib.sha256(raw).hexdigest()
        for kwargs in ({'expected_sha256': '0' * 64, 'parent_slug': 'parent'},
                       {'expected_sha256': digest, 'parent_slug': 'absent'},
                       {'expected_sha256': digest, 'parent_slug': 'parent', 'child_slug': 'other'}):
            with self.assertRaises(ValueError):
                build(raw, **kwargs)
        duplicate = json.dumps({'models': [{'slug': 'parent'}, {'slug': 'parent'}]}).encode()
        with self.assertRaises(ValueError):
            build(duplicate, hashlib.sha256(duplicate).hexdigest(), parent_slug='parent')

    def test_parent_preserved_and_widened_descriptor_rejected_even_with_new_hash(self):
        raw = json.dumps({'models': [{'slug': 'parent', 'marker': 'preserved'}]}).encode()
        value = build(raw, hashlib.sha256(raw).hexdigest(), parent_slug='parent')
        self.assertEqual(value['models'][0], json.loads(raw)['models'][0])
        self.assertEqual(value['models'][1]['apply_patch_tool_type'], 'freeform')
        self.assertIsNone(value['models'][1]['multi_agent_version'])
        value['models'][1]['experimental_supported_tools'] = ['exec_command']
        generated = json.dumps(value).encode()
        with self.assertRaises(ValueError):
            validate_generated(generated, hashlib.sha256(generated).hexdigest(), raw, parent_slug='parent')
