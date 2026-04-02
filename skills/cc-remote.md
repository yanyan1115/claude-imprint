---
name: cc-remote
description: Use cc_execute/cc_check to run tasks on the user's local machine via Claude Code. Triggers when user asks to run commands, check files, play music, do git ops, execute scripts, or anything about doing things on their local machine.
---

# Remote Claude Code Execution

User's local Mac has Claude Code running. Use cc_execute / cc_check MCP tools to make it do things.

## Basic flow

1. `cc_execute(prompt="...")` — task starts async, returns task_id
2. Wait ~15s, then `cc_check(task_id)` — returns result + session_id
3. If status is "running", wait a few seconds and cc_check again

## Multi-turn (follow-up in same context)

Pass session_id from cc_check to keep CC's memory across tasks:

1. `cc_execute(prompt="看一下 xxx 项目的结构")`
2. `cc_check(task_id)` → get result + session_id
3. `cc_execute(prompt="把那个 bug 修一下", session_id="...")` ← CC remembers step 1

Without session_id, CC starts fresh with no context.

## Rules

- Always cc_check to get the real result before replying to user
- CC needs 10-20s to start, don't check too early
- Multi-step work must pass session_id
- Timeout: 5 min, budget: $1 per task
- Tell the user when task is submitted, and again when result is ready
