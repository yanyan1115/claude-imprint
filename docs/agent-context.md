# Agent Context

This file is long-lived context for future Codex/Cursor/agent sessions.

Every new session working on this project must read this file before planning or editing files.

## Repository Layout

This project uses a two-repository architecture.

| Role | Path | Responsibility |
|---|---|---|
| Main framework | `D:\APP\claude-imprint` container, Git root `D:\APP\claude-imprint\claude-imprint` | Integration shell, deployment docs, Dashboard docs, runbooks, hooks, package wrappers, release/integration regression tests. |
| Core memory package | Git root `D:\APP\imprint-memory` | `imprint-memory` Python package, MCP tools, SQLite schema/init, memory/search/reindex logic, core unit tests. |

The main framework depends on the core package through `requirements.txt`:

```text
imprint-memory @ git+https://github.com/Qizhan7/imprint-memory.git
```

For local development in this workspace, treat `D:\APP\imprint-memory` as the editable upstream core package, even when the dependency URL points at GitHub. When running main-framework tests that import `imprint_memory`, set:

```powershell
$env:PYTHONPATH='D:\APP\imprint-memory'
```

## Editing Responsibilities

- Change `D:\APP\claude-imprint\claude-imprint` for documentation, deployment runbooks, integration tests, shell scripts, Dashboard wrappers, and project-level policy.
- Change `D:\APP\imprint-memory` for memory core behavior, MCP tool implementation, SQLite schema/reindex/search logic, and core package tests.
- If a task touches both product behavior and operator docs, update both repositories in the same work session.
- Before committing, check `git status --short` separately in both repositories.

## Phase 5 P2 Status

Phase 5 P2 "retrieval and operations quality hardening" has started.

Completed first slice: SQLite FTS5 rebuild strategy.

Implemented and documented:

- `memory_reindex` now reports observable per-target status.
- Rebuild targets include `memory_vectors`, `memories_fts`, `conversation_log_fts`, and `bank_chunks`.
- FTS rebuild drops/recreates derived FTS5 tables and repopulates them from canonical tables using `segment_cjk()`.
- `bank_chunks` rebuild clears stale rows and re-indexes Markdown bank files.
- Deployment runbook now covers FTS/bank corruption recovery.
- Regression coverage includes CJK + English mixed search recovery examples.

## Verification Pattern

Core package:

```powershell
cd D:\APP\imprint-memory
python -m pytest -q
```

Main framework:

```powershell
cd D:\APP\claude-imprint\claude-imprint
$env:PYTHONPATH='D:\APP\imprint-memory'
python -m pytest -q
```
