from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))

from run_p7_posix_mutation import AGENT_TYPE, invocation, role_text


class PosixMutationPreparationTests(unittest.TestCase):
    def test_invocation_keeps_parent_openai_and_routes_only_exact_child(self):
        command = invocation(
            Path("/private/tmp/candidate"),
            Path("/private/tmp/probe"),
            Path("/private/tmp/role.toml"),
            Path("/private/tmp/models.json"),
        )
        overrides = [
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == "-c"
        ]
        self.assertIn('model_provider="openai"', overrides)
        self.assertIn(
            f'features.multi_agent_v2.child_model_providers.{AGENT_TYPE}="deepseek"',
            overrides,
        )
        self.assertIn('model_providers.deepseek.wire_api="responses"', overrides)
        self.assertIn('model_providers.deepseek.supports_namespace_tools=false', overrides)
        self.assertIn(
            'model_providers.deepseek.requires_function_call_output_adjacency=true',
            overrides,
        )
        self.assertEqual(command[command.index("-a") + 1], "never")
        self.assertEqual(command[command.index("-s") + 1], "workspace-write")
        self.assertNotIn("windows.sandbox", "\n".join(overrides))

    def test_roles_treat_user_consent_as_ceiling_not_lease(self):
        positive = role_text(negative=False)
        negative = role_text(negative=True)
        self.assertIn("User consent is an upper bound, never a lease", positive)
        self.assertIn("Hook-delivered write capsule and writer lease", positive)
        self.assertIn("foreign-path apply_patch", negative)
        self.assertIn("grants no foreign-path ownership", negative)
        self.assertIn("return exactly TASK.CONTEXT_LOST", negative)

    def test_source_chain_receipt_is_part_of_live_manifest_contract(self):
        runner = (ROOT / "probes" / "run_p7_posix_mutation.py").read_text(
            encoding="utf-8"
        )
        verifier = (
            ROOT / "probes" / "verify_p7_posix_mutation_outcome.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--source-chain-receipt", runner)
        self.assertIn("source_chain_receipt_sha256", runner)
        self.assertIn("source patch-chain artifact drift", verifier)


if __name__ == "__main__":
    unittest.main()
