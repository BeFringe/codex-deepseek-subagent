from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-tree-20260912.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def added_file_bytes(patch_text: str, path: str) -> bytes:
    marker = f"diff --git a/{path} b/{path}\n"
    lines = []
    in_section = False
    in_hunk = False
    for line in patch_text.splitlines(keepends=True):
        if line == marker:
            in_section = True
            continue
        if in_section and line.startswith("diff --git "):
            break
        if in_section and line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith("\\ No newline at end of file"):
            lines[-1] = lines[-1].removesuffix("\n")
    if not in_hunk:
        raise AssertionError(f"added file hunk not found for {path}")
    return "".join(lines).encode("utf-8")


class CurrentG4CompleteSourceTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_predecessor_and_ordered_patch_bytes_are_hash_bound(self):
        predecessor = self.receipt["predecessor_receipt"]
        self.assertEqual(sha256(ROOT / predecessor["path"]), predecessor["sha256"])

        for item in self.receipt["ordered_patch_chain"]:
            path = ROOT / item["path"]
            payload = path.read_bytes()
            text = payload.decode("utf-8")
            self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
            self.assertEqual(len(payload), item["bytes"])
            self.assertEqual(len(text.splitlines()), item["lines"])
            self.assertEqual(
                len(re.findall(r"(?m)^diff --git a/.+ b/.+$", text)),
                item["changed_paths"],
            )

    def test_added_files_are_part_of_the_first_patch_and_content_bound(self):
        patch = (
            ROOT / self.receipt["ordered_patch_chain"][0]["path"]
        ).read_text(encoding="utf-8")
        for item in self.receipt["added_paths"]:
            payload = added_file_bytes(patch, item["path"])
            blob = hashlib.sha1(
                f"blob {len(payload)}\0".encode("ascii") + payload
            ).hexdigest()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
            self.assertEqual(blob, item["blob"])
            self.assertIn(
                f"index {'0' * 40}..{item['blob']}",
                patch,
            )

    def test_complete_tree_replaces_but_preserves_the_legacy_observation(self):
        complete = self.receipt["complete_reconstruction"]
        self.assertEqual(
            complete["method"],
            "temporary_index_read_tree_then_apply_cached_in_order",
        )
        self.assertFalse(complete["working_tree_mutated"])
        self.assertTrue(complete["git_apply_cached_passed"])
        self.assertTrue(complete["git_diff_check_passed"])
        self.assertRegex(complete["tree"], r"^[0-9a-f]{40}$")
        self.assertRegex(
            complete["binary_full_index_diff_sha256"], r"^[0-9a-f]{64}$"
        )
        legacy = self.receipt["legacy_tracked_only_observation"]
        self.assertFalse(legacy["complete_source_identity"])
        self.assertEqual(
            set(legacy["omitted_paths"]),
            {item["path"] for item in self.receipt["added_paths"]},
        )
        self.assertNotEqual(
            legacy["sha256"], complete["binary_full_index_diff_sha256"]
        )

    def test_portable_boundary_remains_fail_closed(self):
        boundary = self.receipt["portable_boundary"]
        self.assertTrue(boundary["product_independent"])
        self.assertFalse(boundary["credential_values_recorded"])
        self.assertTrue(boundary["windows_must_match_complete_tree"])
        self.assertFalse(boundary["windows_live_qualified"])
        self.assertFalse(boundary["phase1_complete"])
        self.assertFalse(boundary["direct_write_qualified"])
        self.assertEqual(boundary["phase2_state"], "closed")
        self.assertEqual(boundary["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
