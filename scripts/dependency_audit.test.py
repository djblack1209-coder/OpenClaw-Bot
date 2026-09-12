"""The audit gate must finish every group without disguising scan failures."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("dependency_audit", Path(__file__).with_name("dependency_audit.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditGateTests(unittest.TestCase):
    def run_cases(self, outcomes):
        calls = []

        def command(args, **kwargs):
            calls.append(args[0])
            result = outcomes[len(calls) - 1]
            if isinstance(result, Exception):
                raise result
            code, body = result
            return subprocess.CompletedProcess(args, code, body, "")

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            lock = work / "package-lock.json"
            lock.write_text("{}")
            specs = [
                {"name": str(index), "kind": "npm", "command": [str(index)], "lock": lock, "cwd": work}
                for index in range(len(outcomes))
            ]
            results, code = audit.run_audits(specs, work / "reports", runner=command, timeout=1)
            self.assertEqual(calls, [str(index) for index in range(len(outcomes))])
            saved = json.loads((work / "reports" / "summary.json").read_text())
            self.assertEqual(saved["results"], results)
            return results, code

    @staticmethod
    def npm(high=0, moderate=0):
        return json.dumps({"metadata": {"vulnerabilities": {"high": high, "critical": 0, "moderate": moderate}}, "vulnerabilities": {}})

    def test_findings_do_not_hide_later_groups(self):
        results, code = self.run_cases([(1, self.npm(high=1)), (0, self.npm())])
        self.assertEqual(code, 1)
        self.assertEqual([row["status"] for row in results], ["findings", "passed"])

    def test_missing_tool_does_not_hide_later_groups(self):
        results, code = self.run_cases([FileNotFoundError("fixture"), (0, self.npm())])
        self.assertEqual(code, 1)
        self.assertEqual(results[0]["status"], "incomplete")
        self.assertEqual(results[0]["failure"], "tool_missing")

    def test_timeout_does_not_hide_later_groups(self):
        results, code = self.run_cases([subprocess.TimeoutExpired("fixture", 1), (0, self.npm())])
        self.assertEqual(code, 1)
        self.assertEqual(results[0]["failure"], "timeout")

    def test_damaged_or_tool_error_report_is_not_a_pass(self):
        for body in ("not JSON", "{}", '{"error":{"code":"ENETWORK"}}'):
            with self.subTest(body=body):
                results, code = self.run_cases([(0, body), (0, self.npm())])
                self.assertEqual(code, 1)
                self.assertEqual(results[0]["status"], "incomplete")

    def test_unexpected_exit_is_not_a_pass(self):
        results, code = self.run_cases([(2, self.npm()), (0, self.npm())])
        self.assertEqual(code, 1)
        self.assertEqual(results[0]["status"], "incomplete")

    def test_zero_exit_cannot_hide_high_findings(self):
        results, code = self.run_cases([(0, self.npm(high=1))])
        self.assertEqual(code, 1)
        self.assertEqual(results[0]["status"], "findings")

    def test_all_success_including_visible_below_threshold_findings(self):
        results, code = self.run_cases([(0, self.npm()), (0, self.npm(moderate=2))])
        self.assertEqual(code, 0)
        self.assertEqual(results[1]["counts"]["moderate"], 2)
        self.assertEqual(len(results[0]["lock_sha256"]), 64)

    def test_python_and_rust_malformed_counts_are_rejected(self):
        for kind, report in [
            ('python', {'dependencies': []}),
            ('python', {'dependencies': [{'name': 'fixture', 'version': '1', 'vulns': {}}]}),
            ('rust', {'vulnerabilities': {'count': 0}, 'warnings': {'unsound': 'bad'}}),
        ]:
            with self.subTest(kind=kind, report=report), self.assertRaises(ValueError):
                audit.classify(kind, report)

    def test_python_and_rust_policies_preserved(self):
        counts, failed = audit.classify('python', {'dependencies': [{'name': 'fixture', 'version': '1', 'vulns': [{'id': 'TEST-1'}]}]})
        self.assertTrue(failed)
        self.assertEqual(counts['vulnerabilities'], 1)
        counts, failed = audit.classify('rust', {'vulnerabilities': {'count': 0}, 'warnings': {'unsound': [{}]}})
        self.assertFalse(failed)
        self.assertEqual(counts['warnings'], 1)


if __name__ == "__main__":
    unittest.main()
