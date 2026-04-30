# PRD-to-Schema Gap Table

This document compares `docs/claude-memory-prd-v2.md` with the current Claude Imprint implementation documented in `architecture.md`, `database-schema.md`, `api-reference.md`, and `memory-lifecycle.md`.

Status legend:

| Status | Meaning |
| --- | --- |
| Done | Implemented closely enough for the current PRD behavior. |
| Partial | Present, but naming, lifecycle, UI, or retrieval behavior differs from the PRD. |
| Design choice | Intentional implementation choice; document clearly rather than force a schema change. |
| Backlog | Should be considered for Phase 5 / Phase 6 work. |

## Executive Summary

The core memory model is mostly implemented: emotional fields, decay scoring, surfacing, FTS5, vector storage, conversation logs, summaries, tags, and memory graph edges all exist. The remaining gaps are concentrated in four areas:

1. PRD field names versus actual schema names.
2. Relationship snapshot storage: file-based `CLAUDE.md` instead of a database table.
3. Summary fields exist, but some summary content is not yet consistently consumed by context builders.
4. Graph/tag capabilities exist at MCP/core level but lack Dashboard lifecycle and visualization.

## Gap Table

| PRD entity / relationship | Current implementation | Status | Gap / decision | Recommendation |
| --- | --- | --- | --- | --- |
| `memories.content` | `memories.content` | Done | Core payload exists and is indexed by `memories_fts`. | Keep. |
| `memories.category` with `core_profile`, `task_state`, `episode`, `atomic` | `memories.category` exists; current docs mention categories such as `facts`, `core`, `core_profile`, `tasks`, `events`, `experience`, `general` | Partial | Category taxonomy is broader and not fully normalized to PRD's four-layer model. | Add category mapping docs and optional validator: `facts/core -> core_profile`, `tasks -> task_state`, `events/experience -> episode`, `general -> atomic`. |
| `memories.importance` | `memories.importance` | Done | Used by ranking and decay. Decay archive sets `importance = 0`. | Keep. |
| `memories.subject` (`user` / `ai` / `relation`) | No dedicated column. Subject may be implicit in `content`, `source`, category, or tags. | Backlog | PRD asks for a first-class subject dimension, but schema does not store it. | Add `subject TEXT DEFAULT 'user'` or model it as normalized tags (`subject:user`). Prefer tags first unless Dashboard needs subject filtering. |
| `memories.valence` | `memories.valence REAL DEFAULT 0.5` | Done | Present and editable. | Keep. |
| `memories.arousal` | `memories.arousal REAL DEFAULT 0.3` | Done | Present and used for surfacing / reranking / decay. | Keep. |
| `memories.resolved` | `memories.resolved BOOLEAN DEFAULT 1` | Partial | PRD examples expect `DEFAULT 0`; current default means new MCP memories are resolved unless updated. `memory_remember` does not expose `resolved`. | Expose `resolved` in `memory_remember` or add a second tool/path for unresolved emotional memories. Decide whether DB default should remain `1` for safety. |
| `memories.decay_rate` | `memories.decay_rate REAL DEFAULT 0.05` | Done | Present. Derived by category. | Keep; document category-to-decay mapping. |
| `activation_count` | Actual field is `recalled_count` | Design choice | Same concept, different name. Dashboard exposes compatibility name in some places. | Keep actual field; update PRD/docs to say `activation_count == recalled_count`. |
| `last_active` | Actual field is `last_accessed_at` | Design choice | Same concept, different name. | Keep actual field; update PRD/docs to say `last_active == last_accessed_at`. |
| Archived memory state | No physical `archived` column. Archive is `importance = 0` and `superseded_by = -1`. | Design choice | PRD says low score auto-archives; implementation uses marker fields, not status enum. | Keep for now, but document clearly. Consider a future `status` column only if Dashboard/workflows need it. |
| `decay_score` | Calculated at runtime by `calculate_memory_score()`, not persisted. | Design choice | Dashboard has compatibility checks for optional `decay_score`, but core does not store it. | Keep runtime calculation. Add API field if UI needs display snapshots. |
| L1 relationship snapshot | `$IMPRINT_DATA_DIR/CLAUDE.md` file read by context assembly. No `relationship_snapshots` table. | Design choice | PRD/roadmap mention relationship snapshot layer; implementation chooses a human-maintained Markdown file. | Keep file as source of truth for Phase 5. Add `examples/CLAUDE.md.example` link and Dashboard source indicator. |
| `relationship_snapshots` table | Not implemented. | Backlog | No historical snapshot table, versioning, or timestamps. | Phase 6 candidate: add table only if automatic relationship snapshot history is needed. |
| Rolling summaries | `summaries` table with `content`, `turn_count`, `platform`, `created_at`; Dashboard can list/edit/delete. | Partial | PRD wants "recent summaries" in context. Current summary table exists, but summary generation and MCP update/delete coverage have had drift across docs. | Keep table. Ensure MCP tool docs match actual `save/get/update/delete` support and add automated summary generation acceptance tests. |
| `daily_logs.summary` | `daily_logs.summary` exists. | Partial | Field exists, but automatic daily summary and retrieval/context linkage are not consistently part of the injected context. | Backlog: define whether daily summaries feed `build_context()` or remain archival. |
| `conversation_log.summary` | `conversation_log.summary` exists and hooks may populate it for long non-CC messages. | Partial | `recent_context.md` currently formats recent messages and does not consistently prefer `summary`. | Decide rendering strategy: use `summary` when present for long channel messages, with content fallback. |
| Recent raw conversation layer | `conversation_log`, `recent_context.md`, hooks pipeline. | Done | Cross-channel recent messages are logged and rendered. | Keep. |
| `memory_tags` relationship | `memory_tags(memory_id, tag)` plus `memories.tags` JSON string. | Partial | Core capability exists; Dashboard filtering/visual editing/lifecycle docs are thin. | Add Dashboard tag editor/filter and lifecycle docs. |
| `memory_edges` relationship | `memory_edges(source_id, target_id, relation, context, surfaced_count, used_count)` | Partial | Core graph exists and search can expand neighbors, but Dashboard graph visualization and edge lifecycle are not exposed. | Add graph view or memory detail relation panel; define edge relation taxonomy. |
| Memory vectors | `memory_vectors(memory_id, embedding, model)` | Done | Supports semantic retrieval when embedding provider is available. | Keep. |
| FTS5 memory index | `memories_fts` with CJK segmentation triggers. | Done | FTS exists. | Keep; Phase 5 P2 should handle reindex runbook. |
| Conversation FTS index | `conversation_log_fts` | Done | Search across channel logs exists. | Keep. |
| Knowledge bank | `bank_chunks` for `$IMPRINT_DATA_DIR/memory/bank/*.md` | Done | Not central in PRD, but useful extension. | Keep; document as long-form memory. |
| Active surfacing relationship | `resolved = 0`, `arousal > 0.7`, `importance > 0`, `pinned = 0`, `superseded_by IS NULL` | Done | PRD behavior exists. | Keep; make thresholds configurable through docs/API. |
| Context builder five-layer model | Implemented by `memory_manager.build_context()`, not separate `context_builder.py` | Partial | Layers exist in current docs, but cap is documented as 3000 chars in architecture versus PRD's 2000 tokens. | Treat file/function naming as design choice. Align token/char cap docs and expose config if needed. |
| Memory write extraction prompt | Core write path supports emotional fields, but this repo does not own the external LLM extraction prompt. | Partial | PRD requires stable third-person extraction and empty-result retry. Current `claude-imprint` cannot fully verify external core prompt behavior. | Add regression docs/tests in `memo-clover` or pin expected prompt behavior in API docs. |
| Minimum vector similarity `0.6` | Current architecture docs mention unified search `VEC_PRE_FILTER = 0.3`; older weighted path differs. | Partial | PRD's `0.6` hard threshold is not the current unified search behavior. | Backlog: retrieval evaluation before changing threshold; document actual RRF + prefilter semantics. |
| Weighted retrieval formula `0.6 vector / 0.2 FTS / 0.1 time / 0.1 arousal` | Current unified search uses RRF plus reranking; older path has `0.4 / 0.4 / 0.2`. | Design choice | Implementation diverges from PRD formula but may be more robust. | Keep RRF if quality is better; update PRD to describe actual ranking model. |
| Memory management panel: view/search/edit/delete | Dashboard supports list/search/edit/delete with emotional metadata. | Done | Core management exists. | Keep. |
| Memory management panel: write log / why remembered | Dashboard shows stream and memory records, but no first-class "why remembered" audit trail. | Backlog | PRD asks users to know what was remembered and why. No extraction rationale table/field exists. | Consider `memory_events` or `memories.reason` if auditability becomes a goal. |
| Memory heatmap | Dashboard heatmap uses memories, conversation logs, and daily logs. | Done | Present. | Keep. |
| Multi-user / role isolation | Explicitly out of scope in PRD. | Not applicable | Not implemented. | No action. |
| Non-text memories | Explicitly out of scope in PRD. | Not applicable | Telegram file sending exists, but memory model remains text-first. | No action for P1. |

## Priority Recommendations

### Keep As Design Choices

- Keep `CLAUDE.md` as relationship snapshot source for Phase 5.
- Keep `recalled_count` and `last_accessed_at` as actual schema names; document PRD aliases.
- Keep archive representation as `importance = 0` plus `superseded_by = -1`.
- Keep RRF-based unified search unless retrieval evaluation proves the PRD weighted formula performs better.

### Phase 5 Backlog

1. Expose or document `resolved` at memory creation time.
2. Decide how `conversation_log.summary` should appear in `recent_context.md`.
3. Clarify whether `daily_logs.summary` participates in context injection.
4. Add Dashboard affordances for `memory_tags` and `memory_edges`.
5. Add `subject` as either normalized tag convention or physical column.

### Phase 6 Candidates

1. `relationship_snapshots` history table with timestamps and optional auto-generation.
2. Memory audit trail: why a memory was written, updated, superseded, archived, or surfaced.
3. Retrieval evaluation fixtures for vector threshold, RRF weights, arousal boost, and time decay.
