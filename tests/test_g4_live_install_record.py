import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-install-20260817.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveInstallRecordTests(unittest.TestCase):
    def test_install_record_is_complete_but_non_qualifying(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))

        self.assertEqual(record["schema"], 1)
        self.assertTrue(record["existing_v4_hook_preserved"])
        self.assertFalse(record["live_hook_dispatch_observed"])
        self.assertEqual(record["trust"]["g4_entries"], "pending_user_review")
        self.assertFalse(record["trust"]["trust_hash_forged_or_copied"])
        self.assertTrue(record["rollback"]["performed"])
        self.assertTrue(record["rollback"]["candidate_paths_absent_verified"])
        self.assertTrue(record["rollback"]["diagnostic_receipt_preserved"])
        self.assertTrue(record["rollback"]["reinstalled"])
        self.assertFalse(record["rollback"]["functional_live_reload_observed"])
        self.assertFalse(record["rollback"]["qualifies_exit_receipt"])
        self.assertFalse(record["phase1_complete"])
        self.assertFalse(record["direct_write_qualified"])
        self.assertEqual(record["phase2"], "closed")
        self.assertEqual(record["phase3"], "closed")

        hashes = [
            record["backup"]["hooks_json_sha256"],
            record["backup"]["config_toml_sha256"],
            record["installed"]["hooks_json_sha256"],
            record["installed"]["agent_sha256"],
            *record["installed"]["scripts"].values(),
            record["manual_host_probe"]["receipt_sha256"],
            record["rollback"]["restored_hooks_json_sha256"],
            record["rollback"]["v4_agent_sha256"],
            record["rollback"]["v4_hook_sha256"],
            record["rollback"]["reinstalled_hooks_json_sha256"],
        ]
        self.assertTrue(all(SHA256.fullmatch(value) for value in hashes))


if __name__ == "__main__":
    unittest.main()
