import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "hooks" / "hooks.g4-qualification.posix.example.json"
TARGET_ROLE = "g4_qualification_probe_worker"


class G4HookTemplateTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        self.hooks = self.document["hooks"]

    def test_event_set_and_matchers_are_exact(self):
        self.assertEqual(
            set(self.hooks),
            {"PreToolUse", "PostToolUse", "SubagentStart", "PreCompact", "SubagentStop"},
        )
        self.assertEqual(self.hooks["PreToolUse"][0]["matcher"], "*")
        self.assertEqual(self.hooks["PostToolUse"][0]["matcher"], "apply_patch")
        self.assertEqual(
            self.hooks["SubagentStart"][0]["matcher"],
            f"^{TARGET_ROLE}$",
        )
        self.assertEqual(self.hooks["PreCompact"][0]["matcher"], "*")
        self.assertEqual(
            self.hooks["SubagentStop"][0]["matcher"],
            f"^{TARGET_ROLE}$",
        )

    def test_every_event_uses_one_shared_qualification_command(self):
        commands = []
        context_capable_events = {"PreToolUse", "PostToolUse", "SubagentStart"}
        for event_name, groups in self.hooks.items():
            self.assertEqual(len(groups), 1)
            handlers = groups[0]["hooks"]
            self.assertEqual(len(handlers), 1)
            handler = handlers[0]
            self.assertEqual(handler["type"], "command")
            self.assertEqual(handler["timeout"], 15)
            if event_name in context_capable_events:
                self.assertEqual(handler["additionalContextLimit"], 0)
            else:
                self.assertNotIn("additionalContextLimit", handler)
            commands.append(handler["command"])
        self.assertEqual(len(set(commands)), 1)
        command = commands[0]
        self.assertIn("/absolute/path/to/compatibility_hook.py", command)
        self.assertIn("/absolute/private/path/to/g4-state", command)
        self.assertIn(f"--plaintext-agent-type {TARGET_ROLE}", command)
        self.assertNotRegex(command.lower(), r"api[_-]?key|token|password")

    def test_template_is_an_overlay_not_a_v4_replacement(self):
        serialized = json.dumps(self.document, sort_keys=True)
        self.assertNotIn("v4_flash_worker", serialized)
        self.assertIn("merge with existing user Hooks", self.document["description"])


if __name__ == "__main__":
    unittest.main()
