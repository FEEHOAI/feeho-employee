"""Versioned organization parameters and deterministic execution previews."""
from __future__ import annotations

import json
from pathlib import Path

from .cli import PackageError, read_yaml, write_yaml
from .policy import now_iso

VERSIONS_DIR = "versions"
ROLE_LABELS = {"writer": "文案员工", "reviewer": "内容审核员工", "manager": "内容运营经理", "human-owner": "负责人"}


def default_organization(employee: dict, permissions: dict, acceptance: dict) -> dict:
    denied = "external:publish" in permissions.get("deny", [])
    return {
        "task": {"id": "content-week-01", "objective": employee.get("objective", "")},
        "roles": [
            {"id": "writer", "responsibility": "撰写并修改周三用户案例"},
            {"id": "reviewer", "responsibility": "协助复核事实与品牌口径"},
            {"id": "manager", "responsibility": "审核修改稿并提交负责人批准"},
            {"id": "human-owner", "responsibility": "决定本次发布与最终验收"},
        ],
        "workflow": [
            {"id": "draft", "owner": "writer", "action": "content:draft"},
            {"id": "manager-review", "owner": "manager", "action": "content:review"},
            {"id": "publish-approval", "owner": "human-owner", "action": "external:publish", "status": "not_applicable" if denied else "waiting"},
        ],
        "approval": {"enabled": not denied, "owner": "human-owner", "scope": "once", "status": "not_applicable" if denied else "waiting"},
        "acceptance": {"status": employee.get("status", "draft"), "required_cases": acceptance.get("required_cases", [])},
    }


def organization_changes(before: dict, after: dict) -> list[dict]:
    changes = []
    fields = (
        ("roles", "岗位分工", lambda value: [f"{ROLE_LABELS.get(role['id'], role['id'])}：{role['responsibility']}" for role in value]),
        ("workflow", "任务顺序", lambda value: [f"{ROLE_LABELS.get(step['owner'], step['owner'])}（{step['action']}）" for step in value]),
        ("approval", "审批路径", lambda value: "不再适用" if not value.get("enabled") else f"{ROLE_LABELS.get(value['owner'], value['owner'])} / {value['scope']}"),
        ("acceptance", "验收合同", lambda value: value.get("required_cases", [])),
    )
    for field, label, render in fields:
        old_value, new_value = before.get(field), after.get(field)
        if old_value != new_value:
            changes.append({"field": field, "label": label, "before": render(old_value), "after": render(new_value)})
    return changes


def apply_organization_request(before: dict, request: str) -> tuple[dict, list[dict], list[str]]:
    after = json.loads(json.dumps(before))
    warnings = []
    reviewer_first = "审核员工" in request and "经理复核" in request
    denied = "禁止" in request and "发布" in request
    restore_approval = not denied and ("批准" in request or "不能自行发布" in request or "审批" in request)
    if reviewer_first:
        after["roles"][1]["responsibility"] = "第一审核节点，检查事实与品牌口径"
        after["roles"][2]["responsibility"] = "第二复核节点，复核后提交负责人"
        after["workflow"] = [
            {"id": "draft", "owner": "writer", "action": "content:draft"},
            {"id": "reviewer-check", "owner": "reviewer", "action": "content:review"},
            {"id": "manager-review", "owner": "manager", "action": "content:review"},
            {"id": "publish-approval", "owner": "human-owner", "action": "external:publish", "status": "waiting"},
        ]
        after["acceptance"]["required_cases"] = sorted(set(after["acceptance"]["required_cases"]) | {"reviewer-before-manager", "manager-before-owner"})
    if denied:
        after["workflow"] = [step for step in after["workflow"] if step["id"] != "publish-approval"]
        after["approval"] = {"enabled": False, "owner": "human-owner", "scope": "once", "status": "not_applicable"}
        after["acceptance"]["required_cases"] = [case for case in after["acceptance"]["required_cases"] if case not in {"publish-requires-approval", "manager-before-owner"}]
        after["acceptance"]["required_cases"].append("publish-denied")
    elif restore_approval:
        if not any(step["id"] == "publish-approval" for step in after["workflow"]):
            after["workflow"].append({"id": "publish-approval", "owner": "human-owner", "action": "external:publish", "status": "waiting"})
        after["approval"] = {"enabled": True, "owner": "human-owner", "scope": "once", "status": "waiting"}
        after["acceptance"]["required_cases"] = [case for case in after["acceptance"]["required_cases"] if case != "publish-denied"]
        if "publish-requires-approval" not in after["acceptance"]["required_cases"]:
            after["acceptance"]["required_cases"].append("publish-requires-approval")
    after["acceptance"]["required_cases"] = sorted(set(after["acceptance"]["required_cases"]))
    if not reviewer_first and not denied and not restore_approval:
        warnings.append("未识别到组织分工或审批路径变化。")
    return after, organization_changes(before, after), warnings


def snapshot(root: Path, version: int, request: str, changes: list[dict]) -> dict:
    employee = read_yaml(root / "employee.yaml")
    return {
        "schema_version": "0.3",
        "version": version,
        "created_at": now_iso(),
        "request": request,
        "employee": employee,
        "permissions": read_yaml(root / "permissions.yaml"),
        "organization": read_yaml(root / "organization.yaml"),
        "acceptance": read_yaml(root / "acceptance.yaml"),
        "cases": read_yaml(root / "evals" / "cases.yaml").get("cases", []),
        "changes": changes,
    }


def version_path(root: Path, version: int) -> Path:
    return root / VERSIONS_DIR / f"v{version:03d}.json"


def list_versions(root: Path) -> list[dict]:
    directory = root / VERSIONS_DIR
    if not directory.is_dir():
        return []
    versions = []
    for path in sorted(directory.glob("v*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            versions.append({"version": value["version"], "created_at": value["created_at"], "request": value.get("request", "")})
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise PackageError(f"版本记录损坏：{path.name}") from exc
    return versions


def ensure_history(root: Path, employee: dict, permissions: dict, acceptance: dict, initial_request: str) -> int:
    versions = list_versions(root)
    if versions:
        if not (root / "organization.yaml").is_file():
            raise PackageError("版本记录存在，但 organization.yaml 缺失")
        return versions[-1]["version"]
    organization = default_organization(employee, permissions, acceptance)
    write_yaml(root / "organization.yaml", organization)
    first = snapshot(root, 1, initial_request, [])
    version_path(root, 1).parent.mkdir(parents=True, exist_ok=True)
    version_path(root, 1).write_text(json.dumps(first, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1


def record_history(root: Path, version: int, request: str, changes: list[dict]) -> dict:
    current = snapshot(root, version, request, changes)
    destination = version_path(root, version)
    if destination.exists():
        raise PackageError(f"不可变版本已经存在：v{version:03d}")
    destination.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current


def read_version(root: Path, version: int) -> dict:
    path = version_path(root, version)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackageError(f"版本不存在：v{version:03d}") from exc
    except json.JSONDecodeError as exc:
        raise PackageError(f"版本记录损坏：v{version:03d}") from exc


def simulate_current(root: Path) -> dict:
    organization = read_yaml(root / "organization.yaml")
    permissions = read_yaml(root / "permissions.yaml")
    denied = "external:publish" in permissions.get("deny", [])
    trace = [f"{ROLE_LABELS.get(step['owner'], step['owner'])}：{step['action']}" for step in organization["workflow"] if step["id"] != "publish-approval"]
    return {
        "schema_version": "0.3",
        "mode": "deterministic-simulation-not-model",
        "task_id": organization["task"]["id"],
        "trace": trace,
        "approval": "not_applicable" if denied else "waiting_human",
        "tool_decision": "denied" if denied else "approval_required",
        "generic_agent_baseline": "没有强制组织路径，模型自行决定顺序与边界",
        "next_execution": "发布工具被拦截" if denied else "完成组织路径后，在发布前等待真人批准",
        "note": "这里只根据当前参数计算执行路径，不调用模型，不代表真实任务已经完成。",
    }
