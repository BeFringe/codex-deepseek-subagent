import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


termination_guard = load_module(
    "termination_guard", REPO / "hooks" / "termination_guard.py"
)


class TerminationGuardTests(unittest.TestCase):
    def contract(self):
        resolutions = [
            "UNJOURNALED",
            "BLOCKED",
            "CANCELLED",
            "COMPLETED",
            "TERMINAL_NOOP",
        ]
        return {
            "catalog_closed": True,
            "boundary_catalog": [
                {
                    "boundary_id": f"boundary-{ordinal}",
                    "seam": "fixture.transition",
                    "ordinal": ordinal,
                    "termination_primitive": "os._exit",
                    "expected_durable_resolution": resolution,
                }
                for ordinal, resolution in enumerate(resolutions)
            ],
        }

    def test_closed_catalog_requires_exact_fresh_process_resolution(self):
        contract = self.contract()
        reports = [
            {
                "boundary_id": item["boundary_id"],
                "termination_primitive": "os._exit",
                "terminated_pid": 100 + item["ordinal"],
                "observer_pid": 200 + item["ordinal"],
                "durable_resolution": item["expected_durable_resolution"],
            }
            for item in contract["boundary_catalog"]
        ]

        by_id = {report["boundary_id"]: report for report in reports}
        result = termination_guard.adjudicate_boundary_catalog(
            contract, observe_boundary=lambda boundary: by_id[boundary["boundary_id"]]
        )

        self.assertTrue(result["catalog_complete"])
        self.assertEqual(result["boundary_count"], 5)

    def test_missing_boundary_or_same_process_observer_fails_closed(self):
        contract = self.contract()
        with self.assertRaisesRegex(
            termination_guard.TerminationViolation, "no report"
        ):
            termination_guard.adjudicate_boundary_catalog(
                contract, observe_boundary=lambda boundary: None
            )

        reports = [
            {
                "boundary_id": item["boundary_id"],
                "termination_primitive": "os._exit",
                "terminated_pid": 100 + item["ordinal"],
                "observer_pid": 200 + item["ordinal"],
                "durable_resolution": item["expected_durable_resolution"],
            }
            for item in contract["boundary_catalog"]
        ]
        reports[0]["observer_pid"] = reports[0]["terminated_pid"]
        with self.assertRaisesRegex(
            termination_guard.TerminationViolation, "fresh process"
        ):
            by_id = {report["boundary_id"]: report for report in reports}
            termination_guard.adjudicate_boundary_catalog(
                contract,
                observe_boundary=lambda boundary: by_id[boundary["boundary_id"]],
            )

    def test_real_os_exit_resolution_is_observed_by_a_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "durable-state"
            terminated = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,pathlib; pathlib.Path("
                        + repr(str(state))
                        + ").write_text('UNJOURNALED'); os._exit(31)"
                    ),
                ]
            )
            terminated_pid = terminated.pid
            self.assertEqual(terminated.wait(), 31)
            observed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json,os,pathlib; print(json.dumps({'pid':os.getpid(),"
                        "'resolution':pathlib.Path("
                        + repr(str(state))
                        + ").read_text()}))"
                    ),
                ],
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            )
            observer = json.loads(observed.stdout)
            contract = {
                "catalog_closed": True,
                "boundary_catalog": [
                    {
                        "boundary_id": "before-journal",
                        "seam": "fixture.transition",
                        "ordinal": 0,
                        "termination_primitive": "os._exit",
                        "expected_durable_resolution": "UNJOURNALED",
                    }
                ],
            }
            result = termination_guard.adjudicate_boundary_catalog(
                contract,
                observe_boundary=lambda boundary: {
                        "boundary_id": "before-journal",
                        "termination_primitive": "os._exit",
                        "terminated_pid": terminated_pid,
                        "observer_pid": observer["pid"],
                        "durable_resolution": observer["resolution"],
                    },
            )

            self.assertTrue(result["catalog_complete"])

    def test_os_exit_skips_finally_but_keyboard_interrupt_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os_exit_finally = root / "os-exit-finally"
            interrupt_finally = root / "interrupt-finally"
            os_exit = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,pathlib; p=pathlib.Path(r'"
                        + str(os_exit_finally)
                        + "');\ntry: os._exit(23)\nfinally: p.write_text('ran')"
                    ),
                ],
                check=False,
            )
            interrupted = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import pathlib; p=pathlib.Path(r'"
                        + str(interrupt_finally)
                        + "');\ntry: raise KeyboardInterrupt()\nfinally: p.write_text('ran')"
                    ),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

            self.assertEqual(os_exit.returncode, 23)
            self.assertNotEqual(interrupted.returncode, 0)
            self.assertFalse(os_exit_finally.exists())
            self.assertEqual(interrupt_finally.read_text(), "ran")


if __name__ == "__main__":
    unittest.main()
