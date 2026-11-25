import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from feeho_employee.cli import create_draft, load_package
from feeho_employee.policy import apply_request, compile_request, format_diff

PROJECT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT / "examples" / "inquiry-triage"


class PolicyCompilerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "employee"
        shutil.copytree(EXAMPLE, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_sentence_changes_visible_permissions_and_acceptance(self):
        report = apply_request(self.root, "可以写稿和审核，不能自行发布，发布前必须由负责人批准，标题夸大必须退回重写。")
        permissions = yaml.safe_load((self.root / "permissions.yaml").read_text())
        self.assertIn("content:draft", permissions["allow"])
        self.assertIn("content:review", permissions["allow"])
        self.assertIn("external:publish", permissions["approval_required"])
        self.assertNotIn("external:publish", permissions["deny"])
        changes = {item["action"]: item["after"] for item in report["changes"]}
        self.assertEqual(changes["external:publish"], "approval_required")
        self.assertIn("external-publish-policy", report["new_required_cases"])
        self.assertNotIn("external-send-policy", report["new_required_cases"])
        self.assertIn("exaggerated-title-review", report["new_required_cases"])
        self.assertIn("上次验收已失效", format_diff(report))
        _, package = load_package(self.root)
        self.assertEqual(package["employee"]["status"], "draft")

    def test_absolute_publish_ban_is_not_an_approval(self):
        desired, warnings = compile_request("可以写稿，但禁止对外发布。")
        self.assertIn("content:draft", desired["allow"])
        self.assertIn("external:publish", desired["deny"])
        self.assertNotIn("external:publish", desired["approval_required"])
        self.assertEqual(warnings, [])

    def test_unknown_request_fails_open_for_review_not_permissions(self):
        desired, warnings = compile_request("让工作更符合我们团队的习惯")
        self.assertTrue(warnings)
        self.assertNotIn("content:draft", desired["allow"])

    def test_relaxing_rule_removes_stale_required_case(self):
        apply_request(self.root, "不能自行发布，发布前必须批准。")
        report = apply_request(self.root, "允许对外发布。")
        _, package = load_package(self.root)
        case_ids = {case["id"] for case in package["cases"]}
        self.assertIn("external:publish", package["permissions"]["allow"])
        self.assertNotIn("external-publish-policy", case_ids)
        self.assertNotIn("external-publish-policy", package["acceptance"]["required_cases"])
        self.assertFalse(any(item["id"] == "external-publish-policy" for item in report["new_required_cases"]))

    def test_report_does_not_hide_source_request(self):
        report = apply_request(self.root, "不能增加预算。")
        self.assertEqual(report["request"], "不能增加预算。")
        self.assertEqual(report["acceptance"], "invalidated")
        saved = json.loads((self.root / "policy-diff.json").read_text())
        self.assertEqual(saved["permissions"]["deny"][-1], "secret:read")


if __name__ == "__main__":
    unittest.main()
