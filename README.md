# Claude Imprint

### Turn Claude Code into your personal assistant that lives across all your devices.

A self-hosted system that extends Claude Code with persistent memory, multi-channel chat, and automation. Talk to Claude from Telegram, WeChat, or Claude.ai — it remembers everything, sets reminders, writes code, and manages your day. All data stays on your machine.

Built for **Claude Code Pro/Max subscribers** who want to unlock more from their subscription. Uses only official Claude Code features — no API costs, no third-party authorization. Think of it as a DIY [OpenClaw](https://github.com/openclaw/openclaw), fully local and fully yours.

## Features

- **Unified Memory Across Claude Code and Claude.ai** — The same SQLite memory backend serves both Claude Code (local MCP server) and Claude.ai chat (via Custom Connector + Cloudflare Tunnel). Memories saved in one are instantly available in the other. One brain, multiple interfaces.
- **Custom Memory System (replaces CC's built-in memory)** — Claude Code's default memory is file-based and basic. This project replaces it with a full database-backed system: SQLite + FTS5 full-text search + Ollama bge-m3 vector embeddings. Hybrid retrieval (keyword + semantic + time decay scoring), categorized storage, daily logs, and MCP tools that let Claude autonomously decide when to remember and recall.
- **Search Memories From Any Channel** — Ask Claude to recall something from Telegram, WeChat, or Claude.ai — it searches the same memory database. What you told Claude on your phone is available when you sit down at your computer.
- **Multi-Channel (all optional)** — Pick the channels you need: Telegram, WeChat, Claude.ai, or any future platform (Discord, etc.). Each is independent — install one, two, or all. They all share the same memory and can talk to Claude Code.
- **Chat-to-Code** — Tell Claude from any chat platform to write code, run scripts, or manage your projects. Your messaging app becomes a remote control for Claude Code.
- **Reminders From Chat** — Send a message like "remind me to call the dentist tomorrow at 3pm" from any platform. Claude creates a persistent scheduled task and notifies you on time.
- **Scheduled Tasks** — Persistent tasks (morning briefing, reminders, nightly memory consolidation) using Claude Code's built-in scheduler.
- **Heartbeat Agent** — Periodic automated checks with proactive notifications.
- **Dashboard** — Single-file FastAPI app (localhost:3000). Component status, start/stop controls, memory browser, and an interaction heatmap that shows how often you and Claude talk throughout the day.
- **Pre-compaction Hook** — Automatically saves conversation context before Claude Code compresses the context window.

## Architecture

```
                        ┌─────────────────┐
                        │   memory.db     │  ← single source of truth
                        │  (SQLite local) │
                        └────────┬────────┘
                                 │
                ┌────────────────┼────────────────┐
                │ stdio          │ HTTP            │
                ▼                ▼                 ▼
        Claude Code        Cloudflare Tunnel   Dashboard
        ├── Telegram       → Claude.ai chat    (localhost:3000)
        ├── WeChat            (Custom Connector)
        ├── Scheduled Tasks
        └── CLAUDE.md
```

## Prerequisites

- **Claude Code** (Pro or Max subscription recommended for heavy usage)
- **Python 3.12+**
- **macOS or Linux** — Core features (memory, MCP server, dashboard) work on both. Shell scripts (`start-all.sh`, `stop-all.sh`) use `osascript` to open Terminal windows on macOS; on Linux, replace with your terminal emulator or run each service manually.
- **An always-on machine** — This is a local-first system. All services (memory server, Cloudflare Tunnel, heartbeat, scheduled tasks) run on your machine. If your computer sleeps or shuts down, they stop. For uninterrupted service, consider running on a Mac mini / home server, or disabling sleep (`caffeinate -s` on macOS).

Optional (install only what you need):
- **Telegram Bot** — for Telegram channel
- **WeChat** — via [claude-wechat-channel](https://www.npmjs.com/package/claude-wechat-channel) bridge
- **Cloudflare account** — to connect Claude.ai chat to your local memory
- **Ollama + bge-m3** — for semantic vector search (works without it, keyword-only)

## Quick Start

```bash
# Clone
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint

# (Recommended) Create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Register the memory MCP server (user-level, available in all CC sessions)
claude mcp add -s user imprint-memory -- python3 $(pwd)/memory_mcp.py

# Start the dashboard
python3 dashboard.py
# → http://localhost:3000
```

> **Note:** This guide uses `python3` throughout. If you have multiple Python versions, replace with `python3` or whichever version you have (3.11+ required).

## Setup Guide

### 1. Memory System

The memory system works out of the box after registering the MCP server. Claude will automatically use `memory_remember` and `memory_search` tools.

To enable semantic search (optional):
```bash
# Install Ollama
brew install ollama
ollama pull bge-m3
```

### 2. Write Your CLAUDE.md

Create `~/.claude/CLAUDE.md` — this is what makes Claude yours. Here's a minimal starting template:

```markdown
# My Assistant

## About Me
- Name: [your name]
- Timezone: [e.g., UTC-5, UTC+8]
- Languages: [e.g., English, Chinese]

## Personality
- [How you want Claude to communicate: casual? formal? concise?]
- [Any preferences: no emojis, direct answers, etc.]

## Memory Rules
- Save important information using memory_remember
- Search memory before saying "I don't know"
- Log significant events to the daily log

## Notification Rules
- Telegram chat_id: [your chat ID]
- Quiet hours: 23:00-07:00 (no proactive messages)
- Important events: notify immediately
- Routine updates: batch and wait until asked
```

See the [Customization section](#customization-the-md-files) below for how this file relates to the others.

### 3. Pre-compaction Hook (recommended)

This hook automatically saves conversation context before Claude Code compresses the context window, so important details don't get lost:

```bash
# Register the hook in your Claude Code settings
claude settings add-hook PreCompact "bash $(pwd)/hooks/pre-compact-flush.sh"
```

Or manually add to `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreCompact": [
      { "command": "bash /path/to/claude-imprint/hooks/pre-compact-flush.sh" }
    ]
  }
}
```

### 4. Telegram (optional)

```bash
# Configure your bot token
claude /telegram:configure

# Start Telegram channel
claude --channels plugin:telegram@claude-plugins-official
```

### 5. WeChat (optional)

```bash
# Install the WeChat bridge
npm install -g claude-wechat-channel

# Add to your .mcp.json (see .mcp.json.example)
# Start WeChat channel
claude --dangerously-load-development-channels server:wechat
```

### 6. Claude.ai Chat Integration (optional)

This is the key feature: **Claude.ai chat and Claude Code share the same memory database.** Memories saved in a chat conversation are searchable from Claude Code, and vice versa.

The memory MCP server supports two modes — local stdio (for Claude Code) and HTTP (for Claude.ai via Custom Connector). Both read and write to the same local `memory.db`.

#### Step 1: Start the HTTP memory server

```bash
python3 memory_mcp.py --http
# Runs on localhost:8000
```

This runs alongside the stdio server that Claude Code already uses. They share the same database (SQLite WAL mode handles concurrent access).

#### Step 2: Expose via Cloudflare Tunnel

```bash
brew install cloudflare/cloudflare/cloudflared
cloudflared tunnel login
cloudflared tunnel create my-tunnel
cloudflared tunnel route dns my-tunnel memory.yourdomain.com
```

Or use a free quick tunnel (temporary URL, changes on restart):
```bash
cloudflared tunnel --url http://localhost:8000
```

#### Step 3: Generate OAuth credentials

```bash
python3 -c "
import secrets, json
creds = {
    'client_id': secrets.token_urlsafe(16),
    'client_secret': secrets.token_urlsafe(32),
    'access_token': secrets.token_urlsafe(32),
}
with open('\$HOME/.imprint-oauth.json', 'w') as f:
    json.dump(creds, f, indent=2)
print('Credentials saved to ~/.imprint-oauth.json')
print(f'Client ID: {creds[\"client_id\"]}')
"
```

#### Step 4: Add Custom Connector in Claude.ai

1. Go to **Claude.ai → Settings → Connectors → Add Custom Connector**
2. Enter your tunnel URL
3. In Advanced Settings, enter the OAuth Client ID and Client Secret
4. Click Add — done

Claude.ai now has access to `memory_remember`, `memory_search`, `memory_forget`, `memory_daily_log`, and `memory_list` — the exact same tools Claude Code uses.

#### Step 5: Teach Claude.ai to use the memory

Adding the connector gives Claude.ai access to the tools, but it won't know *when* to use them unless you tell it. A few options:

- **Project instructions** (recommended): Create a Claude.ai Project and add instructions like *"Use `memory_search` to recall context. Use `memory_remember` to save important information."*
- **Custom instructions**: In Claude.ai → Settings → Custom Instructions, add a note about using the memory tools.
- **Just ask**: You can also tell Claude in any conversation to remember or search — it will see the available tools and use them.

Once set up, the workflow is seamless: chat on Claude.ai during the day, switch to Claude Code for coding — same memories, no sync needed.

### 7. Dashboard

```bash
python3 dashboard.py
# Open http://localhost:3000
```

Manages all components from one page: start/stop services, browse memories, view scheduled tasks, interaction heatmap.

### 8. Heartbeat Agent (optional)

The heartbeat agent periodically wakes up Claude Code to perform automated checks (calendar, reminders, proactive notifications).

```bash
# Start the agent
python3 agent.py

# Or with a custom interval (default: 15 minutes)
HEARTBEAT_INTERVAL=300 python3 agent.py   # 5-minute interval for testing
```

The agent reads `SOUL.md` (personality) and `HEARTBEAT.md` (checklist) to know what to check and how to behave. Edit these files to customize its behavior.

> **Tip:** Use `start-all.sh` to launch the heartbeat agent alongside other services, or `start.sh` to run just the agent.

### 9. Scheduled Tasks

Create persistent scheduled tasks through Claude Code:
```
> Create a scheduled task that sends me a morning briefing at 8am via Telegram
```

Tasks survive restarts and are stored in `~/.claude/scheduled-tasks/`.

### 10. Import Chat History (optional)

Already have months of conversations on Claude.ai? You can import them into the memory system so Claude remembers everything from day one.

```bash
# 1. Export from Claude.ai: Settings → Privacy → Export Data
# 2. Unzip the export, find conversations.json
# 3. Run the cleaner to split into manageable sessions
python3 chat_cleaner.py ~/Downloads/claude-export/conversations.json
```

This splits your conversations into session files (in `chat_sessions/`), broken by 6-hour silence gaps. Long sessions are further split with overlap to preserve context.

Then feed each session to Claude Code for memory extraction:
```bash
# For each session file, ask Claude Code to read and remember the important parts
claude "Read chat_sessions/session_001.txt and save any important facts, preferences, or events to memory using memory_remember"
```

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `TZ_OFFSET` | `0` | UTC offset for your timezone (e.g., `12` for NZST, `-5` for EST) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `EMBED_MODEL` | `bge-m3` | Embedding model name |
| `HEARTBEAT_INTERVAL` | `900` | Heartbeat interval in seconds |
| `TELEGRAM_CHAT_ID` | (empty) | Your Telegram chat ID for notifications |
| `QUIET_START` | `23` | Quiet hours start (no proactive messages) |
| `QUIET_END` | `7` | Quiet hours end |

## File Structure

```
claude-imprint/
├── memory_manager.py    # Core memory module (SQLite + vectors + FTS5)
├── memory_mcp.py        # MCP server (stdio + HTTP modes)
├── dashboard.py         # Single-file dashboard (FastAPI + inline HTML)
├── heartbeat.py         # Heartbeat agent module
├── agent.py             # Agent entry point
├── chat_cleaner.py      # Import old Claude.ai conversations
├── hooks/
│   └── pre-compact-flush.sh  # Pre-compaction memory saver
├── memory/              # Daily logs (YYYY-MM-DD.md)
│   └── bank/            # Structured knowledge files
├── SOUL.md              # Heartbeat personality rules
├── HEARTBEAT.md         # Heartbeat checklist
├── MEMORY.md            # Auto-generated memory index
├── start-all.sh         # Start all services
├── stop-all.sh          # Stop all services
└── requirements.txt
```

## Customization: The .md Files

Claude Imprint uses a set of Markdown files that work together to give Claude its personality, behavior rules, and context. Here's what each does and how they relate:

```
~/.claude/CLAUDE.md          ← You write this. The brain.
    │
    ├── references ──→  SOUL.md         ← You write this. Lightweight personality summary.
    ├── references ──→  HEARTBEAT.md    ← You write this. What to check and when to notify.
    └── references ──→  MEMORY.md       ← Auto-generated. Don't edit.
                         memory/bank/   ← You write these. Structured knowledge.
```

### `~/.claude/CLAUDE.md` — The brain (you write this)

This is the most important file. Claude Code reads it at the start of every session. Put everything here that Claude should **always know**:

- Who you are, your preferences, your timezone
- Claude's personality and communication style
- Rules for when to remember, when to notify, when to stay quiet
- Technical preferences and project guidelines

This file lives in `~/.claude/` (not in the project directory) so it applies across all Claude Code sessions.

### `SOUL.md` — Heartbeat personality (you write this)

A lightweight subset of your CLAUDE.md, injected into heartbeat sessions. Heartbeat runs in its own session with limited context, so it needs a compact version of the personality rules. Keep it short — just behavior rules and notification preferences.

### `HEARTBEAT.md` — Heartbeat checklist (you write this)

Defines what the heartbeat agent checks on each wake-up: morning briefing, routine monitors, notification channels, quiet hours. Edit this to add your own automated checks.

### `MEMORY.md` — Memory index (auto-generated)

Auto-generated by `memory_manager.py`. Provides a quick overview of what's stored in `memory.db`. Don't edit manually — it gets overwritten.

### `memory/bank/` — Structured knowledge (you write these)

Long-form knowledge files that get indexed for semantic search:

- **`preferences.md`** — Your preferences, habits, dietary needs, etc.
- **`experience.md`** — Technical lessons learned, debugging insights
- **`relationships.md`** — People you mention, their roles and context

Claude can search these via the memory tools. Add your own files here for any category you want.

### `memory/YYYY-MM-DD.md` — Daily logs (auto-generated)

Created automatically by the `memory_daily_log` tool and the pre-compaction hook. One file per day, append-only. You don't need to edit these.

### Getting Started

1. Copy the example files in this repo as a starting point
2. Write your `~/.claude/CLAUDE.md` — this is where you define who Claude is to you
3. Edit `SOUL.md` and `HEARTBEAT.md` to match your preferences
4. Add your info to `memory/bank/preferences.md`
5. The rest (MEMORY.md, daily logs) will populate automatically as you use the system

## How It Compares to OpenClaw

OpenClaw is a mature, feature-rich project with a large plugin ecosystem. Claude Imprint takes a different approach — minimal, Claude Code-native, and fully local.

| | OpenClaw | Claude Imprint |
|---|---|---|
| Approach | Platform with plugin ecosystem | Lightweight, Claude Code-native |
| AI models | 20+ providers (Claude, GPT, Gemini...) | Claude only (via Claude Code) |
| Data location | Depends on provider | Fully local |
| Multi-channel | 20+ (WhatsApp, Slack, Discord...) | Telegram + WeChat + Claude.ai |
| Setup | npm install, hosted options available | Self-hosted, manual setup |
| Best for | Users who want a ready-to-go platform | Users who want full control over a Claude Code-based setup |

## Acknowledgements

- [OpenClaw](https://github.com/openclaw/openclaw) — Multi-model personal AI assistant framework that inspired this project
- [Anthropic](https://anthropic.com) — Claude Code, MCP protocol, and the Telegram plugin
- [FastMCP](https://github.com/jlowin/fastmcp) / [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — MCP server framework
- [claude-wechat-channel](https://www.npmjs.com/package/claude-wechat-channel) — WeChat bridge for Claude Code
- [Ollama](https://ollama.com) + [bge-m3](https://huggingface.co/BAAI/bge-m3) — Local embedding model for semantic search

## License

[MIT](LICENSE)
