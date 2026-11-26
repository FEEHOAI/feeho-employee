import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from feeho_employee.cli import evaluate, load_package, read_yaml
from feeho_employee.history import list_versions, read_version, simulate_current
from feeho_employee.policy import apply_request
from feeho_employee.runtime import export_adapter

PROJECT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT / "examples" / "content-operations"
REVIEW = "周三用户案例先由审核员工检查，经理复核后才能交给我批准。"
DENY = "禁止对外发布。"


class OrganizationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "employee"
        shutil.copytree(EXAMPLE, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_review_change_has_full_diff_version_and_execution_preview(self):
        report = apply_request(self.root, REVIEW)
        fields = {change["field"] for change in report["changes"] if "field" in change}
        self.assertEqual(fields, {"roles", "workflow", "acceptance"})
        self.assertEqual(report["version"], 3)
        self.assertEqual(report["next_execution"]["trace"], ["文案员工：content:draft", "内容审核员工：content:review", "内容运营经理：content:review"])
        self.assertEqual(report["next_execution"]["tool_decision"], "approval_required")
        self.assertEqual([item["version"] for item in list_versions(self.root)], [1, 2, 3])
        snapshot = read_version(self.root, 3)
        self.assertEqual(snapshot["organization"]["acceptance"]["required_cases"], read_yaml(self.root / "acceptance.yaml")["required_cases"])
        self.assertEqual(snapshot["organization"]["workflow"][1]["owner"], "reviewer")
        self.assertIn("required_sequence", json.dumps(snapshot["cases"]))

    def test_deny_removes_approval_and_versions_remain_immutable(self):
        apply_request(self.root, REVIEW)
        first = read_version(self.root, 1)
        report = apply_request(self.root, DENY)
        self.assertEqual(report["version"], 4)
        self.assertFalse(report["organization"]["approval"]["enabled"])
        self.assertFalse(any(step["id"] == "publish-approval" for step in report["organization"]["workflow"]))
        self.assertIn("external:send", report["permissions"]["approval_required"])
        self.assertNotIn("external:send", report["permissions"]["deny"])
        self.assertEqual(report["new_required_cases"], [])
        self.assertEqual(report["next_execution"]["tool_decision"], "denied")
        self.assertEqual(read_version(self.root, 1), first)
        self.assertEqual([item["version"] for item in list_versions(self.root)], [1, 2, 3, 4])
        self.assertEqual(simulate_current(self.root)["approval"], "not_applicable")

    def test_required_sequence_passes_and_wrong_order_fails(self):
        apply_request(self.root, REVIEW)
        results = json.loads((self.root / "sample-results.json").read_text())
        results["cases"]["reviewer-before-manager"] = {"output": "顺序正确", "tool_calls": ["reviewer:content:review", "manager:content:review"], "escalated": False}
        results["cases"]["manager-before-owner"] = {"output": "顺序正确", "tool_calls": ["reviewer:content:review", "manager:content:review", "human-owner:approval"], "escalated": False}
        path = Path(self.temp.name) / "results.json"
        path.write_text(json.dumps(results, ensure_ascii=False))
        root, package = load_package(self.root)
        report = evaluate(root, package, path, Path(self.temp.name) / "report.json")
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["passed"], 6)
        results["cases"]["manager-before-owner"]["tool_calls"] = ["manager:content:review", "reviewer:content:review", "human-owner:approval"]
        path.write_text(json.dumps(results, ensure_ascii=False))
        report = evaluate(root, package, path, Path(self.temp.name) / "failed.json")
        self.assertFalse(report["ok"])
        self.assertTrue(any("required execution sequence" in failure for case in report["cases"] for failure in case["failures"]))

    def test_propose_does_not_touch_original_package(self):
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = subprocess.run([sys.executable, "-m", "feeho_employee.cli", "propose", str(self.root), "--request", DENY], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("只读预览", result.stdout)
        self.assertIn("审批路径", result.stdout)
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_diff_history_simulate_and_cc_command(self):
        apply_request(self.root, REVIEW)
        apply_request(self.root, DENY)
        result = subprocess.run([sys.executable, "-m", "feeho_employee.cli", "diff", str(self.root), "--from", "3", "--to", "4"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("v3 → v4", result.stdout)
        self.assertIn("审批路径", result.stdout)
        result = subprocess.run([sys.executable, "-m", "feeho_employee.cli", "simulate", str(self.root), "--json"], capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["tool_decision"], "denied")
        export_adapter(self.root, sys.executable)
        command = self.root / ".claude" / "commands" / "feeho.md"
        self.assertTrue(command.is_file())
        self.assertIn("feeho propose", command.read_text())


if __name__ == "__main__":
    unittest.main()
