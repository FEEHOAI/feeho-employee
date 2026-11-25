# Changelog

## 0.2.0 — 2026-11-26

### Added

- Deterministic Chinese requirement compiler with visible permission diffs and explicit warnings.
- Acceptance invalidation and new required cases after policy changes.
- Claude Code `PreToolUse` adapter with fail-closed tool checks and official exit-code-2 blocking.
- One-time, expiring human grants issued outside the agent, with file-locked consumption.
- Protection against credential reads, self-approval and policy modification.
- Audit records that exclude tool contents and are never included in exported employee ZIPs.
- Content-operations example and a reproducible Claude Code comparison guide.
- 22 automated tests covering policy compilation, runtime boundaries and existing package contracts.

### Security boundary

- The hook is a tool policy layer, not an OS sandbox. Enterprise MCP tools still require explicit action mappings.

## 0.1.0 — 2026-11-25

### Changed

- Open-source core is now distributed under the MIT License. Commercial use is permitted without a separate FEEHO license.
- Canonical repository links now use `FEEHOAI/feeho-employee`.

### Added

- Deterministic generic employee draft scaffolding.
- Employee metadata JSON Schema and safe YAML validation.
- Permission conflict, handoff and acceptance-contract checks.
- External agent result evaluation for outputs, tools, handoffs and escalation.
- JSON evaluation reports with explicit human-review boundary.
- Portable ZIP export with symlink and path-safety checks.
- Fictional inquiry-triage example, sample results and nine unit tests.
- MIT licensing, contribution, security and commercial-boundary documentation.

### Known limits

- No model execution, organization scheduler, enterprise approval system or platform-specific exporter.
- Contract tests alone do not establish broad model quality or production readiness.
