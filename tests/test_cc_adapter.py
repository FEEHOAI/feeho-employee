import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from feeho_employee.policy import apply_request
from feeho_employee.runtime import audit, create_grant, evaluate_tool, export_adapter, runtime_path

PROJECT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT / "examples" / "inquiry-triage"


class ClaudeCodeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "employee"
        shutil.copytree(EXAMPLE, self.root)
        apply_request(self.root, "可以写稿和审核，不能自行发布，发布前必须由负责人批准，禁止读取密钥。")

    def tearDown(self):
        self.temp.cleanup()

    def test_publish_is_blocked_before_tool_execution(self):
        result = evaluate_tool(self.root, "mcp__social__publish_post", {"content": "draft"})
        self.assertFalse(result["allow"])
        self.assertEqual(result["decision"], "approval_required")

    def test_unmapped_mcp_tool_requires_approval(self):
        result = evaluate_tool(self.root, "mcp__custom__unknown_action", {})
        self.assertFalse(result["allow"])
        self.assertEqual(result["action"], "external:write")

    def test_one_time_human_grant_is_consumed(self):
        grant = create_grant(self.root, "external:publish")
        first = evaluate_tool(self.root, "mcp__social__publish_post", {})
        second = evaluate_tool(self.root, "mcp__social__publish_post", {})
        self.assertTrue(first["allow"])
        self.assertEqual(first["grant_id"], grant["id"])
        self.assertFalse(second["allow"])

    def test_agent_cannot_approve_itself_or_rewrite_policy(self):
        approve = evaluate_tool(self.root, "Bash", {"command": "feeho approve . --action external:publish --yes"})
        rewrite = evaluate_tool(self.root, "Write", {"file_path": str(self.root / "permissions.yaml")})
        organization = evaluate_tool(self.root, "Write", {"file_path": str(self.root / "organization.yaml")})
        version = evaluate_tool(self.root, "Edit", {"file_path": str(self.root / "versions" / "v002.json")})
        self.assertEqual(approve["action"], "permission:self-modify")
        self.assertFalse(approve["allow"])
        self.assertEqual(rewrite["action"], "permission:self-modify")
        self.assertFalse(rewrite["allow"])
        self.assertFalse(organization["allow"])
        self.assertFalse(version["allow"])

    def test_propose_diff_and_simulate_are_safe_for_agent(self):
        for command in ("feeho propose . --request 禁止发布", "feeho diff .", "feeho simulate ."):
            result = evaluate_tool(self.root, "Bash", {"command": command})
            self.assertTrue(result["allow"], command)
        configure = evaluate_tool(self.root, "Bash", {"command": "feeho configure . --request 禁止发布"})
        self.assertFalse(configure["allow"])

    def test_secret_read_is_denied_and_audit_contains_no_file_contents(self):
        result = evaluate_tool(self.root, "Read", {"file_path": "/customer/.env", "secret_value": "do-not-log"})
        self.assertFalse(result["allow"])
        audit(self.root, "Read", result["action"], result["decision"], result["reason"])
        logged = runtime_path(self.root, "audit.jsonl").read_text()
        self.assertIn("secret:read", logged)
        self.assertNotIn("do-not-log", logged)
        self.assertNotIn("/customer/.env", logged)

    def test_hook_returns_documented_block_exit_code(self):
        settings = export_adapter(self.root, sys.executable)
        self.assertTrue(settings.is_file())
        payload = json.dumps({"tool_name": "mcp__social__publish_post", "tool_input": {}})
        result = subprocess.run([sys.executable, "-m", "feeho_employee.cc_hook", "--package", str(self.root)], input=payload, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("审批门", result.stderr)

    def test_export_never_contains_grants_or_audit(self):
        import zipfile
        from feeho_employee.cli import export_package
        create_grant(self.root, "external:publish")
        destination = Path(self.temp.name) / "employee.zip"
        export_adapter(self.root, sys.executable)
        export_package(self.root, destination)
        with zipfile.ZipFile(destination) as archive:
            names = archive.namelist()
        self.assertTrue(any(name.endswith(".claude/settings.json") for name in names))
        self.assertFalse(any(".feeho-runtime" in name for name in names))

    def test_adapter_preserves_existing_hooks(self):
        destination = self.root / ".claude" / "settings.json"
        destination.parent.mkdir()
        destination.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 existing.py"}]}]}}))
        export_adapter(self.root, sys.executable)
        settings = json.loads(destination.read_text())
        commands = [hook["command"] for group in settings["hooks"]["PreToolUse"] for hook in group["hooks"]]
        self.assertIn("python3 existing.py", commands)
        self.assertEqual(len(commands), 2)


if __name__ == "__main__":
    unittest.main()
