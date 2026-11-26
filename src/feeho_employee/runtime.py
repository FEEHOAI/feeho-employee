"""Claude Code PreToolUse adapter and one-time human approval grants.

The hook uses Claude Code's documented exit code 2 to block a tool call and
return stderr to the agent. It is a policy layer, not an OS sandbox.
"""
from __future__ import annotations

import json
import os
import re
import sys
import fcntl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .cli import PackageError, load_package
from .policy import now_iso

RUNTIME_DIR = ".feeho-runtime"
PROTECTED_NAMES = {"employee.yaml", "permissions.yaml", "organization.yaml", "acceptance.yaml", "cases.yaml", "role.md", "instructions.md", "settings.json", "policy-diff.json", "feeho-policy.json"}
SECRET_PATTERN = re.compile(r"(?:^|[\s/\\'\"])(?:\.env(?:\..*)?|id_rsa|id_ed25519|[^\s/\\]*(?:secret|credential|token)[^\s/\\]*)(?=$|[\s/\\'\"])|\.(?:pem|key)(?:$|[\s'\"])", re.I)
PUBLISH_PATTERN = re.compile(r"publish|post(?:ing)?|upload|发布|推送", re.I)
SEND_PATTERN = re.compile(r"send|email|smtp|message|外发|发送", re.I)
NETWORK_COMMAND = re.compile(r"(?:^|[;&|]\s*)(?:curl|wget|http|https)\b|\b(?:curl|wget|http)\s+", re.I)


def runtime_path(root: Path, name: str) -> Path:
    return root / RUNTIME_DIR / name


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise PackageError(f"运行时记录损坏：{path.name}") from exc


def write_private_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def audit(root: Path, tool_name: str, action: str, decision: str, reason: str, grant_id: str | None = None) -> None:
    destination = runtime_path(root, "audit.jsonl")
    destination.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": now_iso(), "tool": tool_name, "action": action, "decision": decision, "reason": reason}
    if grant_id:
        record["grant_id"] = grant_id
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass


def create_grant(path: str | Path, action: str, ttl_minutes: int = 10) -> dict:
    root, package = load_package(path)
    if action not in package["permissions"].get("approval_required", []):
        raise PackageError(f"该动作不属于审批范围：{action}")
    if not 1 <= ttl_minutes <= 60:
        raise PackageError("授权有效期必须在 1-60 分钟之间")
    import uuid
    grant = {"id": str(uuid.uuid4()), "action": action, "created_at": now_iso(), "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat().replace("+00:00", "Z"), "used": False}
    grants = read_json(runtime_path(root, "grants.json"), [])
    grants.append(grant)
    write_private_json(runtime_path(root, "grants.json"), grants)
    audit(root, "human-terminal", action, "granted", "真人签发一次性授权", grant["id"])
    return grant


def consume_grant(root: Path, action: str) -> dict | None:
    path = runtime_path(root, "grants.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with runtime_path(root, "grant.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        grants = read_json(path, [])
        current = datetime.now(timezone.utc)
        for grant in grants:
            if grant.get("used") or grant.get("action") != action:
                continue
            try:
                expires = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if expires <= current:
                continue
            grant["used"] = True
            grant["used_at"] = now_iso()
            write_private_json(path, grants)
            return grant
    return None


def classify_tool(tool_name: str, tool_input: dict) -> tuple[str, str]:
    lowered = tool_name.lower()
    file_path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    command = str(tool_input.get("command") or "")
    target = file_path or command
    if SECRET_PATTERN.search(target):
        return "secret:read", "尝试访问密钥或凭证文件"
    if any(target.endswith(name) or f"/{name}" in target or f"\\{name}" in target for name in PROTECTED_NAMES) or RUNTIME_DIR in target or "/versions/" in target or "\\versions\\" in target:
        return "permission:self-modify", "尝试修改员工权限、适配器或运行记录"
    if tool_name == "Bash" and re.search(r"\bfeeho\s+(approve|configure)\b", command):
        return "permission:self-modify", "Agent 不能自行签发授权或修改权限"
    if tool_name in {"Read", "Glob", "Grep"}:
        return "read:provided-documents", "读取已提供资料"
    if PUBLISH_PATTERN.search(lowered) or (NETWORK_COMMAND.search(command) and PUBLISH_PATTERN.search(command)):
        return "external:publish", "尝试对外发布"
    if SEND_PATTERN.search(lowered) or (NETWORK_COMMAND.search(command) and SEND_PATTERN.search(command)):
        return "external:send", "尝试对外发送"
    if tool_name == "WebFetch" or lowered.startswith("mcp__") or (NETWORK_COMMAND.search(command) and re.search(r"(?:-X\s*(?:POST|PUT|PATCH|DELETE)|--request\s+(?:POST|PUT|PATCH|DELETE)|--data|-d\s)", command, re.I)):
        return "external:write", "外部系统写入或未显式映射的 MCP 工具"
    return "tool:other", "普通工具调用"


def evaluate_tool(root: Path, tool_name: str, tool_input: dict) -> dict:
    _, package = load_package(root)
    permissions = package["permissions"]
    action, reason = classify_tool(tool_name, tool_input)
    if action in permissions.get("deny", []):
        return {"allow": False, "action": action, "reason": f"FEEHO 权限拦截：{reason}。该动作被员工合同明确禁止。", "decision": "denied"}
    if action in permissions.get("approval_required", []):
        grant = consume_grant(root, action)
        if not grant:
            return {"allow": False, "action": action, "reason": f"FEEHO 审批门：{reason}需要真人批准。请真人在 Agent 外运行 feeho approve . --action {action} --yes，再重试。一次性授权不会扩大长期权限。", "decision": "approval_required"}
        return {"allow": True, "action": action, "reason": "一次性真人授权已核销", "decision": "granted_once", "grant_id": grant["id"]}
    return {"allow": True, "action": action, "reason": reason, "decision": "allowed"}


def hook_main(root: Path) -> int:
    try:
        raw = sys.stdin.read(1_000_001)
        if len(raw) > 1_000_000:
            raise PackageError("Hook 输入超过 1MB")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("tool_name"), str) or not isinstance(payload.get("tool_input", {}), dict):
            raise PackageError("无效的 PreToolUse 输入")
        tool_name = payload["tool_name"]
        result = evaluate_tool(root, tool_name, payload.get("tool_input", {}))
        audit(root, tool_name, result["action"], result["decision"], result["reason"], result.get("grant_id"))
        if not result["allow"]:
            print(result["reason"], file=sys.stderr)
            return 2
        return 0
    except (json.JSONDecodeError, PackageError, OSError, ValueError) as exc:
        print(f"FEEHO 安全失败关闭：{exc}", file=sys.stderr)
        return 2


def export_adapter(path: str | Path, python_executable: str = "python3") -> Path:
    if not python_executable or any(char in python_executable for char in "\n\r;\0"):
        raise PackageError("无效的 Python 可执行文件路径")
    root, _ = load_package(path)
    destination = root / ".claude" / "settings.json"
    existing = read_json(destination, {})
    existing.setdefault("permissions", {}).setdefault("deny", [])
    for rule in ("Read(./.env)", "Read(./**/.env)", "Read(./**/*.pem)", "Read(./**/*.key)"):
        if rule not in existing["permissions"]["deny"]:
            existing["permissions"]["deny"].append(rule)
    command = f'"{python_executable}" -m feeho_employee.cc_hook --package .'
    groups = existing.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if not any(command in hook.get("command", "") for group in groups for hook in group.get("hooks", [])):
        groups.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    command_path = root / ".claude" / "commands" / "feeho.md"
    command_path.parent.mkdir(parents=True, exist_ok=True)
    if not command_path.exists():
        command_path.write_text("""---
description: 只读预览 FEEHO 组织与权限 Diff
argument-hint: "<一句要改变的要求>"
---

请按顺序执行，不要自己编造参数或修改合同文件：

1. 运行 `feeho propose . --request "$ARGUMENTS"`，向用户展示只读 Diff、验收影响和下一次执行路径。
2. 明确告诉用户：当前只是预览，员工包没有被修改，Agent 不能自行应用或批准。
3. 如果用户决定应用，请用户在 Agent 外部终端运行输出中的 `feeho configure` 命令。
4. 应用后可运行 `feeho history .`、`feeho diff .` 和 `feeho simulate .` 核对版本与实际执行边界。
5. 涉及发布或其他审批动作时，真人必须在 Agent 外部运行 `feeho approve`。Agent 不得代替真人签发授权。

FEEHO generated command; safe to regenerate with `feeho cc`.
""", encoding="utf-8")
    return destination
