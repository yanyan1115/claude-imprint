# API Reference

This document describes the currently implemented external interfaces:

1. `imprint-memory` core MCP tools.
2. `claude-imprint` Dashboard HTTP API.

Source of truth:

- `D:\APP\imprint-memory\imprint_memory\server.py`
- `D:\APP\imprint-memory\imprint_memory\memory_manager.py`
- `D:\APP\imprint-memory\imprint_memory\conversation.py`
- `D:\APP\imprint-memory\imprint_memory\bus.py`
- `D:\APP\imprint-memory\imprint_memory\tasks.py`
- `D:\APP\claude-imprint\claude-imprint\packages\imprint_dashboard\dashboard.py`

No unimplemented tools are documented here. In particular:

- There is no MCP `update_summary` tool.
- There is no MCP `delete_summary` tool.
- Dashboard HTTP does implement summary update and delete routes.

---

## Conventions

### MCP Tools

The `imprint-memory` MCP server is exposed by:

```bash
imprint-memory
imprint-memory --http
```

All tools in `imprint_memory.server` return plain text strings to the MCP caller. Some lower-level functions return dictionaries internally, but the public MCP tool wrappers format them as text.

Examples in this section show tool arguments as JSON-like objects because MCP clients pass structured arguments.

### Dashboard HTTP API

The Dashboard runs as a FastAPI application:

```bash
python3 packages/imprint_dashboard/dashboard.py
```

Default URL:

```text
http://localhost:3000
```

All Dashboard API paths are relative to this origin.

---

# Part 1: imprint-memory MCP Tools

## Tool Summary

| Group | Tools |
|---|---|
| Memory CRUD | `memory_remember`, `memory_search`, `memory_forget`, `memory_daily_log`, `memory_list`, `memory_delete`, `memory_update` |
| Memory audit / maintenance | `memory_find_duplicates`, `memory_reindex`, `memory_find_stale`, `memory_decay`, `memory_surface` |
| Context continuity | `get_relationship_snapshot`, `save_summary`, `get_recent_summaries`, `build_context` |
| Pin / graph | `memory_pin`, `memory_unpin`, `memory_add_tags`, `memory_add_edge`, `memory_get_graph` |
| Message bus | `message_bus_read`, `message_bus_post` |
| Conversation search | `conversation_search`, `search_telegram`, `search_channel` |
| Remote Claude Code tasks | `cc_execute`, `cc_check`, `cc_tasks` |
| Knowledge bank | `experience_append` |

---

## Memory CRUD Tools

### `memory_remember`

Stores a new memory.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `content` | `str` | required | Memory text. |
| `category` | `str` | `"general"` | Memory category. Tool doc lists `facts/events/tasks/experience/general`; core code also supports categories such as `core` and `core_profile` for zero decay. |
| `source` | `str` | `"cc"` | Source label, such as `cc`, `chat`, or `api`. |
| `importance` | `int` | `5` | Importance score stored in `memories.importance`. |
| `valence` | `float` | `0.5` | Emotional valence, clamped to `0..1`. |
| `arousal` | `float` | `0.3` | Emotional intensity, clamped to `0..1`. |

Return format: text string.

Possible outputs include:

- `Remembered [category]: content...`
- `Duplicate memory, skipped`
- `Semantically similar memory exists (ID ..., similarity ...). Use update_memory to update it.`

Example:

```json
{
  "content": "User prefers concise Chinese explanations for deployment steps.",
  "category": "facts",
  "source": "cc",
  "importance": 7,
  "valence": 0.7,
  "arousal": 0.4
}
```

Example output:

```text
Remembered [facts]: User prefers concise Chinese explanations for deploy...
```

Implementation notes:

- `memory_remember` does not expose the internal `resolved` argument; `remember()` defaults `resolved=True`.
- `decay_rate` is derived from category by `_decay_rate_for_category()`.

---

### `memory_search`

Searches across memory, knowledge bank, and conversation pools using unified search.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | `str` | required | Search query. |
| `limit` | `int` | `10` | Max formatted results. |
| `after` | `Optional[str]` | `None` | Optional ISO-style lower timestamp/date bound. |
| `before` | `Optional[str]` | `None` | Optional ISO-style upper timestamp/date bound. |

Return format: text string.

Example:

```json
{
  "query": "deployment dashboard memory fields",
  "limit": 5,
  "after": "2026-04-01",
  "before": null
}
```

Example output:

```text
[Memory|facts|2026-04-29] (1.0) Dashboard shows Phase 2 emotional fields...
[Conversation|telegram|2026-04-28] ...
```

If no results:

```text
No matching results found
```

or, when `IMPRINT_LOCALE=zh`:

```text
没有找到匹配的结果
```

---

### `memory_forget`

Deletes all memories whose `content` contains a keyword.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `keyword` | `str` | required | Substring used in `WHERE content LIKE ?`. |

Return format: text string.

Example:

```json
{
  "keyword": "temporary test memory"
}
```

Example outputs:

```text
Deleted 2 memories containing 'temporary test memory'
```

```text
No memories found containing 'temporary test memory'
```

---

### `memory_daily_log`

Appends text to today's daily log row in `daily_logs`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `text` | `str` | required | Text to append to today's daily log. |

Return format: text string.

Example:

```json
{
  "text": "Dashboard metadata editing was deployed and verified."
}
```

Example output:

```text
Logged to 2026-04-29
```

The exact date depends on `TZ_OFFSET`.

---

### `memory_list`

Lists memories newest first.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `category` | `Optional[str]` | `None` | Optional category filter. |
| `limit` | `int` | `20` | Max number of rows. |
| `after` | `Optional[str]` | `None` | Optional lower timestamp/date bound. |
| `before` | `Optional[str]` | `None` | Optional upper timestamp/date bound. |

Return format: text string.

Example:

```json
{
  "category": "facts",
  "limit": 10,
  "after": "2026-04-01",
  "before": null
}
```

Example output:

```text
[12] [facts|cc] User prefers concise Chinese explanations.  (2026-04-29 10:30:00)
```

If empty:

```text
No memories yet
```

---

### `memory_delete`

Deletes one memory by ID.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `memory_id` | `int` | required | Memory ID. |

Return format: text string.

Example:

```json
{
  "memory_id": 12
}
```

Example outputs:

```text
Deleted memory #12
```

```text
Error: Memory 12 not found
```

---

### `memory_update`

Updates a memory by ID.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `memory_id` | `int` | required | Memory ID. |
| `content` | `str` | `""` | New content. Empty string means keep existing content. |
| `category` | `str` | `""` | New category. Empty string means keep existing category. |
| `importance` | `int` | `0` | New importance. `0` means keep existing importance. |
| `resolved` | `int` | `-1` | `-1` keeps current value; `0` marks unresolved; `1` marks resolved. |

Return format: text string.

Example:

```json
{
  "memory_id": 12,
  "content": "User wants architecture docs generated from actual code.",
  "category": "tasks",
  "importance": 8,
  "resolved": 0
}
```

Example outputs:

```text
Updated memory #12
```

```text
Error: Memory 12 not found
```

Important limitation:

- This MCP tool does not expose `valence`, `arousal`, `pinned`, or `decay_rate`.
- Dashboard HTTP `PUT /api/memories/{memory_id}` does support editing those metadata fields when columns exist.

---

## Memory Audit And Maintenance Tools

### `memory_find_duplicates`

Finds semantically similar memory pairs.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `threshold` | `float` | `0.85` | Cosine similarity threshold. |

Return format: text string.

Example:

```json
{
  "threshold": 0.9
}
```

Example output:

```text
Found 1 similar pairs:

  [0.923] #4 (facts) vs #9 (facts)
    A: User prefers concise replies.
    B: User likes short direct answers.
```

If empty:

```text
No similar memory pairs found above threshold
```

---

### `memory_reindex`

Rebuilds all memory embeddings using the current embedding provider.

Parameters: none.

Return format: text string.

Example:

```json
{}
```

Example output:

```text
Reindexed 42/42 memories (0 failed). Provider: ollama, model: bge-m3
```

---

### `memory_find_stale`

Finds potentially stale memories.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `days` | `int` | `14` | Age threshold. |

Return format: text string.

Example:

```json
{
  "days": 30
}
```

Example output:

```text
Found 2 low-activity memories:

  #8 [events] imp=4 recalled=0 (2026-03-01 09:00:00)
    Old project note...
```

If empty:

```text
No low-activity memories older than 30 days
```

---

### `memory_decay`

Archives inactive memories using the emotional forgetting curve.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `days` | `int` | `30` | Passed through to `decay_memories()`, but the current decay implementation scores all eligible rows and uses each row's own timestamps. |
| `dry_run` | `bool` | `true` | Preview only if `true`; apply archive updates if `false`. |

Return format: text string.

Example:

```json
{
  "days": 30,
  "dry_run": true
}
```

Example output:

```text
[DRY RUN] Scanned: 20, Threshold: 0.3, Archived: 1

Archived (importance -> 0):
  #17 [experience] score=0.2410 2 -> 0 — Old low-activity note...
```

Archive semantics:

- Apply mode sets `importance = 0`.
- Apply mode sets `superseded_by = -1`.

---

### `memory_surface`

Returns unresolved high-arousal memories that should be proactively surfaced.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `limit` | `int` | `3` | Max memories returned. |

Return format: text string.

Example:

```json
{
  "limit": 3
}
```

Example output:

```text
Found 1 memories to surface:

  #21 [events] arousal=0.90 valence=0.35 (2026-04-28 22:10:00)
    User was worried about deployment reliability...
```

If empty:

```text
No unresolved high-arousal memories to surface
```

---

## Context Continuity Tools

### `get_relationship_snapshot`

Reads the relationship snapshot from:

```text
$IMPRINT_DATA_DIR/CLAUDE.md
```

Parameters: none.

Return format: text string.

Example:

```json
{}
```

Example output if the file exists:

```text
We are continuing an ongoing collaboration...
```

If missing:

```text
No relationship snapshot found. Create CLAUDE.md in ~/.imprint/ directory.
```

---

### `save_summary`

Saves a rolling conversation summary.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `content` | `str` | required | Summary content. Trimmed and truncated to 1500 characters. |
| `turn_count` | `int` | `0` | Number of conversation turns summarized. |
| `platform` | `str` | `"unknown"` | Source platform label. |

Return format: text string.

Example:

```json
{
  "content": "We reviewed Dashboard Phase 2 metadata editing and deployed it.",
  "turn_count": 18,
  "platform": "cc"
}
```

Example output:

```text
Summary #5 saved (68 chars)
```

If content is empty:

```text
Error: Empty summary content
```

---

### `get_recent_summaries`

Reads recent summaries newest first.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `limit` | `int` | `3` | Max summaries returned. |

Return format: text string.

Example:

```json
{
  "limit": 3
}
```

Example output:

```text
[2026-04-29 11:00:00|cc] (18 turns)
We reviewed Dashboard Phase 2 metadata editing and deployed it.
---
[2026-04-28 22:00:00|telegram] (10 turns)
...
```

If empty:

```text
No conversation summaries yet
```

---

### `build_context`

Builds a compact conversation-start context document.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | `str` | `""` | Optional query used to include relevant memory search results. |

Return format: text string.

Example:

```json
{
  "query": "dashboard memory metadata"
}
```

Output sections can include:

- `=== 连续性规则 ===`
- `=== 关系快照 ===`
- `=== 最近摘要 ===`
- `=== 主动浮现记忆 ===`
- `=== 相关记忆 ===`

If no context beyond continuity rules exists:

```text
No context available yet. This appears to be a fresh start.
```

---

## Pin, Tag, And Graph Tools

### `memory_pin`

Pins a memory so it bypasses time decay.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `memory_id` | `int` | required | Memory ID. |

Return format: text string.

Example:

```json
{
  "memory_id": 12
}
```

Example output:

```text
Pinned memory #12
```

If many memories are already pinned, output may include a warning.

---

### `memory_unpin`

Unpins a memory.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `memory_id` | `int` | required | Memory ID. |

Return format: text string.

Example:

```json
{
  "memory_id": 12
}
```

Example output:

```text
Unpinned memory #12
```

---

### `memory_add_tags`

Adds comma-separated tags to a memory.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `memory_id` | `int` | required | Memory ID. |
| `tags` | `str` | required | Comma-separated tags. |

Return format: text string.

Example:

```json
{
  "memory_id": 12,
  "tags": "dashboard,phase2,metadata"
}
```

Example output:

```text
Added tags to memory #12: dashboard, phase2, metadata
```

If no tags are provided:

```text
Error: provide at least one tag
```

---

### `memory_add_edge`

Creates a typed relationship between two memories.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source_id` | `int` | required | First memory ID. |
| `target_id` | `int` | required | Second memory ID. |
| `relation` | `str` | required | Relation label. |
| `context` | `str` | required | Explanation of the relationship. |

Return format: text string.

Example:

```json
{
  "source_id": 12,
  "target_id": 18,
  "relation": "evolution",
  "context": "The second memory updates the earlier dashboard requirement."
}
```

Example output:

```text
Created edge #3: memory #12 <-> #18 (evolution)
```

Possible errors include:

- `Error: Cannot create edge to self`
- `Error: Memory <id> not found`
- `Error: Edge already exists (edge #...)`

---

### `memory_get_graph`

Shows tags and connected edges for a memory.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `memory_id` | `int` | required | Memory ID. |

Return format: text string.

Example:

```json
{
  "memory_id": 12
}
```

Example output:

```text
Memory #12 graph
  Tags: dashboard, phase2
  Edges (1):
    -> #18 [evolution] Updated dashboard metadata editing...
      context: The second memory updates the earlier dashboard requirement.  (surfaced:1, used:0)
```

---

## Message Bus Tools

### `message_bus_read`

Reads recent message bus entries.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `limit` | `int` | `20` | Max messages. |

Return format: text string.

Example:

```json
{
  "limit": 10
}
```

Example output:

```text
# Recent Messages

[2026-04-29 11:30:00] [cc_task] -> [Task#4 completed] Updated docs...
```

If empty:

```text
(No recent messages)
```

---

### `message_bus_post`

Writes one message to the message bus.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source` | `str` | required | Free-form source label. |
| `direction` | `str` | required | Usually `in` or `out`. |
| `content` | `str` | required | Message content. Auto-truncated to 200 characters by `bus_post()`. |

Return format: text string.

Example:

```json
{
  "source": "api",
  "direction": "out",
  "content": "Dashboard docs generated."
}
```

Example output:

```text
Written to message bus
```

---

## Conversation Search Tools

### `conversation_search`

Searches conversation history.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | `str` | required | Search terms. |
| `platform` | `str` | `""` | Optional exact platform filter. Empty searches all platforms. |
| `limit` | `int` | `20` | Max results. |

Return format: text string.

Example:

```json
{
  "query": "dashboard metadata",
  "platform": "cc",
  "limit": 20
}
```

Example output:

```text
[2026-04-29 11:10:00] cc← Please update the Dashboard memory panel...
```

If empty:

```text
没有找到相关对话记录
```

---

### `search_telegram`

Searches Telegram and heartbeat conversations.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | `str` | required | Search terms. |
| `limit` | `int` | `20` | Max results. |

Return format: text string.

Example:

```json
{
  "query": "morning briefing",
  "limit": 10
}
```

Implementation uses `platforms=["telegram", "heartbeat"]`.

---

### `search_channel`

Searches one platform in `conversation_log`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | `str` | required | Search terms. |
| `channel` | `str` | required | Platform name as stored in `conversation_log.platform`. |
| `limit` | `int` | `20` | Max results. |

Return format: text string.

Example:

```json
{
  "query": "deployment",
  "channel": "telegram",
  "limit": 20
}
```

---

## Remote Claude Code Task Tools

### `cc_execute`

Submits an async task to a local Claude Code process.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `prompt` | `str` | required | Task prompt for Claude Code. |
| `session_id` | `str` | `""` | Optional prior Claude Code session ID for continuation. |

Return format: text string.

Example:

```json
{
  "prompt": "Run tests and summarize failures.",
  "session_id": ""
}
```

Example output:

```text
Task submitted (ID: 4), CC is running
Use cc_check(task_id=4) to get results and session_id
```

Implementation notes:

- Inserts into `cc_tasks`.
- Runs a daemon thread.
- Invokes `claude -p <prompt> --permission-mode auto --output-format json --max-budget-usd 1.00`.
- Timeout is 300 seconds.

---

### `cc_check`

Checks one submitted task.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `task_id` | `int` | required | Task ID returned by `cc_execute`. |

Return format: text string.

Example:

```json
{
  "task_id": 4
}
```

Example output:

```text
Task #4
Status: completed
Session ID: abc123
Created: 2026-04-29 11:20:00
Started: 2026-04-29 11:20:01
Completed: 2026-04-29 11:20:30

--- Result ---
Tests passed.
```

If still running:

```text
Still running... call cc_check again in a few seconds.
```

---

### `cc_tasks`

Lists recent tasks.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `limit` | `int` | `5` | Max tasks. |

Return format: text string.

Example:

```json
{
  "limit": 5
}
```

Example output:

```text
[done] #4 [completed] sid=abc123... Run tests and summarize failures.
[running] #5 [running] Update docs...
```

If empty:

```text
No tasks
```

---

## Knowledge Bank Tool

### `experience_append`

Appends an entry to:

```text
$IMPRINT_DATA_DIR/memory/bank/experience.md
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `title` | `str` | required | Markdown section heading. |
| `content` | `str` | required | Markdown body. |

Return format: text string.

Example:

```json
{
  "title": "Dashboard metadata editing",
  "content": "- Added Phase 2 emotional fields to the Dashboard.\n- Kept old DB compatibility through PRAGMA table_info."
}
```

Example output:

```text
Added experience: Dashboard metadata editing
```

---

# Part 2: Dashboard HTTP API

## Component Names

Component routes use the following `{component}` path values:

| Component key | Type | Meaning |
|---|---|---|
| `memory_http` | `background` | `imprint-memory --http`, checked by port `8000`. |
| `tunnel` | `background` | `cloudflared tunnel run my-tunnel`. |
| `telegram` | `terminal` | Claude Code Telegram channel process. |

---

## `GET /api/status`

Returns process/service status, tunnel status, memory counts, and scheduled task metadata.

Query parameters: none.

Response JSON:

```json
{
  "components": {
    "memory_http": {
      "running": true,
      "pid": 1234,
      "name": "🧠 Memory HTTP",
      "type": "background"
    },
    "tunnel": {
      "running": false,
      "pid": null,
      "name": "🌐 Cloudflare Tunnel",
      "type": "background"
    },
    "telegram": {
      "running": true,
      "pid": 5678,
      "name": "📨 Telegram",
      "type": "terminal"
    }
  },
  "tunnel_url": "Active",
  "memory": {
    "count": 42,
    "today_logs": 5
  },
  "tasks": [
    {
      "id": "morning-briefing",
      "name": "morning-briefing",
      "description": "..."
    }
  ]
}
```

Notes:

- `tunnel_url` is `"Active"` when tunnel process is running, otherwise `null`.
- `memory.count` counts rows in `memories`.
- `memory.today_logs` counts non-empty lines in today's daily log file.

---

## `POST /api/{component}/start`

Starts one configured component.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `component` | `str` | One of `memory_http`, `tunnel`, `telegram`. |

Request body: none.

Success response:

```json
{
  "ok": true,
  "pid": 1234
}
```

For macOS terminal components, success may be:

```json
{
  "ok": true
}
```

Error response for unknown component:

```json
{
  "error": "unknown component"
}
```

HTTP status: `404`.

---

## `POST /api/{component}/stop`

Stops one configured component.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `component` | `str` | One of `memory_http`, `tunnel`, `telegram`. |

Request body: none.

Success response:

```json
{
  "ok": true
}
```

macOS terminal component response can include:

```json
{
  "ok": true,
  "message": "Please close the terminal window manually (Ctrl+C)"
}
```

Unknown component returns:

```json
{
  "error": "unknown component"
}
```

HTTP status: `404`.

---

## `GET /api/heatmap`

Returns daily interaction counts.

Query parameters: none.

Response JSON:

```json
{
  "days": [
    {
      "date": "2026-04-28",
      "count": 3
    },
    {
      "date": "2026-04-29",
      "count": 7
    }
  ]
}
```

Counts combine:

- `memories` grouped by `DATE(created_at)`.
- `conversation_log` grouped by `DATE(created_at)`, if the table exists.
- Non-empty non-heading lines in daily log files under `$IMPRINT_DATA_DIR/memory/YYYY-MM-DD.md`.

---

## `GET /api/memories`

Searches or lists memory rows for the Dashboard.

Query parameters:

| Name | Type | Default | Meaning |
|---|---|---|---|
| `q` | `str` | `""` | Optional content substring search. |
| `limit` | `int` | `20` | Max rows. Clamped to `1..100`. |

Response JSON:

```json
{
  "memories": [
    {
      "id": 12,
      "content": "User prefers concise Chinese deployment explanations.",
      "category": "facts",
      "source": "cc",
      "importance": 7,
      "created_at": "2026-04-29 10:30:00",
      "valence": 0.7,
      "arousal": 0.4,
      "resolved": true,
      "decay_rate": 0.0,
      "pinned": false,
      "activation_count": 1,
      "last_active": null,
      "decay_status": {
        "key": "protected",
        "label": "Protected",
        "zh": "不衰减"
      }
    }
  ]
}
```

Notes:

- The route dynamically inspects `PRAGMA table_info(memories)`.
- Missing fields are returned with Dashboard defaults.
- Optional fields are returned only if physically present: `archived`, `is_archived`, `decay_score`, `status`.
- Current core schema uses `recalled_count` and `last_accessed_at`, but this Dashboard route currently exposes compatibility names `activation_count` and `last_active`.
- If `memory.db` or `memories` table is missing, returns `{"memories": []}`.

---

## `GET /api/decay-status`

Returns lightweight Dashboard counters based on `/api/memories` data.

Query parameters: none.

Response JSON:

```json
{
  "total": 42,
  "protected": 5,
  "surfacing": 2,
  "resolved": 30,
  "archived": 1,
  "decaying": 34,
  "low_score": 0
}
```

Status rules in current code:

| Counter | Rule |
|---|---|
| `total` | Count of memories returned by `_fetch_memories(limit=100000)`. |
| `protected` | Single-item `decay_status.key == "protected"`. |
| `surfacing` | `resolved` is false and `arousal >= 0.7`, independent of single-item status. |
| `resolved` | `resolved` is true. |
| `archived` | `archived` / `is_archived` truthy, or `status` normalized to `archived`, `archive`, or `is_archived`. |
| `decaying` | Single-item `decay_status.key == "decaying"`. |
| `low_score` | Single-item `decay_status.key == "low_score"`. |

---

## `GET /api/summaries`

Lists or searches rolling summaries.

Query parameters:

| Name | Type | Default | Meaning |
|---|---|---|---|
| `q` | `str` | `""` | Optional search over `content` or `platform`. |
| `limit` | `int` | `10` | Max rows. Clamped to `1..100`. |

Response JSON:

```json
[
  {
    "id": 5,
    "content": "We reviewed Dashboard memory metadata editing.",
    "turn_count": 18,
    "platform": "cc",
    "created_at": "2026-04-29 11:00:00"
  }
]
```

If the database or table is missing:

```json
[]
```

---

## `DELETE /api/summaries/{summary_id}`

Deletes one summary.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `summary_id` | `int` | Summary ID. |

Request body: none.

Success response:

```json
{
  "ok": true
}
```

Error examples:

```json
{
  "ok": false,
  "error": "database not found"
}
```

```json
{
  "ok": false,
  "error": "summary not found"
}
```

---

## `PUT /api/summaries/{summary_id}`

Updates one summary.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `summary_id` | `int` | Summary ID. |

Request body:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `content` | `str` | yes | New summary content. Trimmed; empty content is rejected. |
| `platform` | `str` | no | New platform. Defaults to `"unknown"`. |
| `turn_count` | `int` | no | New turn count. Invalid values become `0`; negative values are clamped to `0`. |

Example request:

```json
{
  "content": "Updated rolling summary text.",
  "platform": "cc",
  "turn_count": 20
}
```

Success response:

```json
{
  "ok": true
}
```

Error examples:

```json
{
  "ok": false,
  "error": "content is required"
}
```

```json
{
  "ok": false,
  "error": "summary not found"
}
```

---

## `DELETE /api/memories/{memory_id}`

Deletes one memory through `imprint_memory.memory_manager.delete_memory()`.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `memory_id` | `int` | Memory ID. |

Request body: none.

Success response from current core:

```json
{
  "ok": true
}
```

Error response:

```json
{
  "ok": false,
  "error": "Memory 12 not found"
}
```

HTTP status is `404` when the error text contains `not found`, otherwise `400`.

---

## `PUT /api/memories/{memory_id}`

Updates one memory for Dashboard editing.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `memory_id` | `int` | Memory ID. |

Request body:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `content` | `str` | no | New content. If any core field is supplied, empty content is rejected. |
| `category` | `str` | no | New category. Defaults to `"general"` if core update runs and value is empty. |
| `importance` | `int` | no | Clamped to `1..10`. |
| `valence` | `float` | no | Updated only if `memories.valence` exists. Clamped to `0..1`. |
| `arousal` | `float` | no | Updated only if `memories.arousal` exists. Clamped to `0..1`. |
| `resolved` | `bool` or bool-like | no | Updated only if `memories.resolved` exists. Stored as `1` or `0`. |
| `pinned` | `bool` or bool-like | no | Updated only if `memories.pinned` exists. Stored as `1` or `0`. |
| `decay_rate` | `float`, `null`, or `""` | no | Updated only if `memories.decay_rate` exists. Empty string or null stores `NULL`; negative numbers are clamped to `0`. Non-numeric values return error. |

Example request:

```json
{
  "content": "User wants generated docs to match actual code.",
  "category": "tasks",
  "importance": 8,
  "valence": 0.6,
  "arousal": 0.5,
  "resolved": false,
  "pinned": false,
  "decay_rate": 0.02
}
```

Success response:

```json
{
  "ok": true
}
```

Error examples:

```json
{
  "ok": false,
  "error": "database not found"
}
```

```json
{
  "ok": false,
  "error": "content is required"
}
```

```json
{
  "ok": false,
  "error": "decay_rate must be a non-negative number"
}
```

Notes:

- Core fields `content`, `category`, and `importance` are updated through `mem.update_memory()`.
- Emotional metadata fields are updated directly through SQLite after dynamic column detection.
- Metadata fields absent from old databases are skipped safely.

---

## `GET /api/stream-stats`

Returns conversation stream statistics.

Query parameters: none.

Response JSON:

```json
{
  "total": 120,
  "today": 8,
  "platforms": {
    "cc": 80,
    "telegram": 40
  },
  "last_message": {
    "platform": "telegram",
    "direction": "in",
    "content": "Latest message preview...",
    "time": "2026-04-29 11:35:00"
  }
}
```

If database is missing:

```json
{
  "total": 0,
  "today": 0,
  "platforms": {},
  "last_message": null
}
```

---

## `GET /api/remote-tools`

Returns recent `cc_tasks` rows.

Query parameters: none.

Response JSON:

```json
{
  "tasks": [
    {
      "id": 4,
      "prompt": "Run tests",
      "status": "completed",
      "result": "Tests passed",
      "source": "chat",
      "created_at": "2026-04-29 11:20:00",
      "completed_at": "2026-04-29 11:20:30"
    }
  ]
}
```

If database or table is missing:

```json
{
  "tasks": []
}
```

---

## `GET /api/logs/{component}`

Returns recent log lines for a component.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `component` | `str` | Component key. Only components with `log_file` return real logs. |

Query parameters:

| Name | Type | Default | Meaning |
|---|---|---|---|
| `lines` | `int` | `30` | Number of trailing lines. |

Response JSON:

```json
{
  "logs": "last log lines..."
}
```

Possible fallback values:

```json
{
  "logs": "No logs"
}
```

```json
{
  "logs": "Log file not found"
}
```

---

## `GET /api/system-status`

Returns Dashboard-level system activity counters.

Query parameters: none.

Response JSON:

```json
{
  "last_heartbeat": "2026-04-29 08:00",
  "today_messages": 12,
  "days_active": 7,
  "total_messages": 240
}
```

Sources:

- `conversation_log`
- recent Claude Code JSONL files under `~/.claude/projects`
- `logs/cron-*.log`

---

## `GET /api/memory-fragment`

Returns one random memory fragment with `importance >= 3`.

Query parameters: none.

Response JSON:

```json
{
  "fragment": {
    "content": "User prefers concise deployment instructions.",
    "category": "facts",
    "date": "2026-04-29"
  }
}
```

If no memory exists:

```json
{
  "fragment": null
}
```

---

## `GET /api/short-term-memory`

Parses `recent_context.md` for the Horizon panel.

Query parameters: none.

When no context file exists:

```json
{
  "exists": false,
  "summaries": [],
  "messages": [],
  "total_lines": 0,
  "msg_count": 0
}
```

When context exists:

```json
{
  "exists": true,
  "updated": "2026-04-29 11:40:00",
  "summaries": [
    "[summary] compressed text"
  ],
  "messages": [
    "[04-29 11:35 tg/in] hello"
  ],
  "total_lines": 10,
  "msg_count": 8,
  "summarized_count": 1,
  "summary_count": 1,
  "threshold": 120
}
```

Lookup order:

1. `$IMPRINT_DATA_DIR/recent_context.md`
2. project root `recent_context.md`

---

## `GET /api/live-files`

Returns monitored Markdown/config files with metadata and content.

Query parameters: none.

Response JSON:

```json
{
  "files": [
    {
      "key": "claude_md",
      "label": "CLAUDE.md",
      "desc": "Persona + system config",
      "exists": true,
      "size": 1234,
      "mtime": "04-29 11:40",
      "content": "# Claude...",
      "stale": false
    }
  ]
}
```

Tracked keys:

| Key | Path |
|---|---|
| `claude_md` | `~/.claude/CLAUDE.md` |
| `recent_context` | `$IMPRINT_DATA_DIR/recent_context.md`, with project-root fallback |
| `memory_index` | `$IMPRINT_DATA_DIR/MEMORY.md` |
| `daily_log` | `$IMPRINT_DATA_DIR/memory/YYYY-MM-DD.md` |
| `experience` | `$IMPRINT_DATA_DIR/memory/bank/experience.md` |
| `backlog` | `$IMPRINT_DATA_DIR/memory/bank/backlog.md` |

`stale` is true when file modification age is over 60 minutes.

---

## `GET /api/todos/system`

Reads system todos.

Query parameters: none.

Response JSON:

```json
{
  "content": "- [ ] Example system task"
}
```

Lookup order:

1. `$IMPRINT_DATA_DIR/memory/bank/system-todos.md`
2. `$IMPRINT_DATA_DIR/memory/bank/north-todos.md`

If neither exists:

```json
{
  "content": ""
}
```

---

## `GET /api/todos/backlog`

Reads user backlog.

Query parameters: none.

Response JSON:

```json
{
  "content": "- [ ] Ship docs"
}
```

Path:

```text
$IMPRINT_DATA_DIR/memory/bank/backlog.md
```

If missing:

```json
{
  "content": ""
}
```

---

## `PUT /api/todos/backlog`

Saves user backlog content.

Request body:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `content` | `str` | no | New Markdown content. Defaults to empty string. |

Example request:

```json
{
  "content": "- [ ] Generate api-reference.md\n- [ ] Review docs"
}
```

Success response:

```json
{
  "ok": true
}
```

The route creates `$IMPRINT_DATA_DIR/memory/bank/` if needed.

---

## `GET /`

Renders the single-page Dashboard HTML.

Response type:

```text
text/html
```

The page contains embedded CSS, JavaScript, bilingual labels, modal editors, and all client-side calls to the API routes documented above.

