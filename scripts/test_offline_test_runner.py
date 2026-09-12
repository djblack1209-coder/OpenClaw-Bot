"""Synthetic fixtures verify the offline runner never copies arbitrary config."""

import tempfile
import unittest
from pathlib import Path

from run_clawbot_offline_tests import copy_test_source, copy_tokenizer_data


class CopyBoundaryTests(unittest.TestCase):
    def test_scheduled_sources_are_copied_without_runtime_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            root, copied = Path(directory) / "source", Path(directory) / "copied"
            scripts = {
                "intel_production_cycle.py", "intel_collect_once.py", "intel_worker_remote_run.py",
                "intel_worker_bundle.py", "intel_launch_package.py", "intel_launchagent_next_run_readiness.py",
            }
            expected = {f"packages/clawbot/scripts/{name}" for name in scripts}
            paths = expected | {"packages/clawbot/data/runs/scheduler-state/2026-09-12.json"}
            for name in paths:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic fixture")
            copy_test_source(root, copied, paths)
            actual = {str(path.relative_to(copied)) for path in copied.rglob("*") if path.is_file()}
            self.assertEqual(actual, expected)

    def test_corrupt_vocabulary_is_rejected_before_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = 'venv/lib/python3.12/site-packages/litellm/litellm_core_utils/tokenizers'
            file = root / relative / '9b5ad71b2ce5302211f9c61530b329a4922fc6a4'
            file.parent.mkdir(parents=True)
            file.write_bytes(b'synthetic invalid vocabulary')
            with self.assertRaises(ValueError):
                copy_tokenizer_data(root / 'venv/bin/python', root / 'output')
            self.assertFalse((root / 'output').exists())


    def test_only_named_config_and_source_are_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root, copied = Path(directory) / "source", Path(directory) / "copied"
            names = [
                "config/llm_routing.json",
                "config/client_keys.json",
                "config/nested/llm_routing.json",
                "config/.env",
                "src/core/example.py",
                "tests/fixture.py",
                "data/private.json",
                "scripts/intel_scheduler_gate_probe.py",
                "scripts/intel_scheduled_sandbox.py",
                "scripts/arbitrary.py",
                "scripts/intel_telegram_sandbox_probe.py",
                "scripts/intel_telegram_summary_probe.py",
                "multi_main.py",
                "private.py",
                "scripts/intel_telegram_update_processor_sandbox.py",
                "assets/intel/openclaw-intel-brief-dark.jpg",
                "assets/private.jpg",
            ]
            paths = [f"packages/clawbot/{name}" for name in names]
            for name in paths:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic fixture")
            link = root / "packages/clawbot/src/linked.py"
            link.symlink_to(root / paths[1])
            copy_test_source(root, copied, paths + ["packages/clawbot/src/linked.py"])
            actual = {
                str(path.relative_to(copied))
                for path in copied.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, {paths[0], paths[4], paths[5], paths[7], paths[8], paths[10], paths[11], paths[12], paths[14], paths[15]})


if __name__ == "__main__":
    unittest.main()
