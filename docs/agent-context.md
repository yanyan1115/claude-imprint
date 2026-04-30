# Agent Context

This file is long-lived context for future Codex/Cursor/agent sessions.

Every new session working on this project must read this file before planning or editing files.

## Repository Layout

This project uses a two-repository architecture.

| Role | Path | Responsibility |
|---|---|---|
| Main framework | `D:\APP\claude-imprint` container, Git root `D:\APP\claude-imprint\claude-imprint` | Integration shell, deployment docs, Dashboard docs, runbooks, hooks, package wrappers, release/integration regression tests. |
| Core memory package | Git root `D:\APP\MemoClover` | `memo-clover` Python package, MCP tools, SQLite schema/init, memory/search/reindex logic, core unit tests. |

The main framework depends on the core package through `requirements.txt`:

```text
memo-clover @ git+https://github.com/Qizhan7/MemoClover.git
```

For local development in this workspace, treat `D:\APP\MemoClover` as the editable upstream core package, even when the dependency URL points at GitHub. When running main-framework tests that import `memo_clover`, set:

```powershell
$env:PYTHONPATH='D:\APP\MemoClover'
```

## Editing Responsibilities

- Change `D:\APP\claude-imprint\claude-imprint` for documentation, deployment runbooks, integration tests, shell scripts, Dashboard wrappers, and project-level policy.
- Change `D:\APP\MemoClover` for memory core behavior, MCP tool implementation, SQLite schema/reindex/search logic, and core package tests.
- If a task touches both product behavior and operator docs, update both repositories in the same work session.
- Before committing, check `git status --short` separately in both repositories.

## Phase 5 Status

Phase 5 P1/P2 has been archived and pushed in both repositories.

Completed hardening includes SQLite FTS5 rebuild strategy.

Implemented and documented:

- `memory_reindex` now reports observable per-target status.
- Rebuild targets include `memory_vectors`, `memories_fts`, `conversation_log_fts`, and `bank_chunks`.
- FTS rebuild drops/recreates derived FTS5 tables and repopulates them from canonical tables using `segment_cjk()`.
- `bank_chunks` rebuild clears stale rows and re-indexes Markdown bank files.
- Deployment runbook now covers FTS/bank corruption recovery.
- Regression coverage includes CJK + English mixed search recovery examples.

## MemoClover Rename Status

The core memory package has been renamed from `imprint-memory` / `imprint_memory` to MemoClover:

- Distribution and CLI: `memo-clover`
- Python import package: `memo_clover`
- Core Git root: `D:\APP\MemoClover`

## Verification Pattern

Core package:

```powershell
cd D:\APP\MemoClover
python -m pytest -q
```

Main framework:

```powershell
cd D:\APP\claude-imprint\claude-imprint
$env:PYTHONPATH='D:\APP\MemoClover'
python -m pytest -q
```
