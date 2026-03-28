---
name: setup-memory
description: Guide through initializing the memory system
triggers:
  - setup memory
  - configure memory
  - initialize memory
---

# Setup Memory System

Guide the user through setting up Claude Imprint's core memory system.

## Prerequisites
- Python 3.10+
- Optional: Ollama with bge-m3 model for semantic search

## Steps

### 1. Install and Register MCP Server
```bash
pip install git+https://github.com/Qizhan7/imprint-memory.git
```

Add to `.mcp.json` in the project root (or `~/.claude/.mcp.json` for global):
```json
{
  "mcpServers": {
    "imprint-memory": {
      "command": "imprint-memory"
    }
  }
}
```

### 2. Test Basic Operations
```
memory_remember("Test memory", category="general")
memory_search("test")
memory_list()
```

### 3. Optional: Enable Semantic Search
Install and start Ollama with the bge-m3 embedding model:
```bash
ollama pull bge-m3
ollama serve  # runs on localhost:11434 by default
```
Set custom URL if needed: `export OLLAMA_URL=http://localhost:11434`

### 4. Optional: Enable HTTP Mode (for Claude.ai remote access)
Start the memory server in HTTP mode:
```bash
imprint-memory --http
```
This serves on port 8000. Use Cloudflare Tunnel or similar to expose it.

For OAuth, create `~/.imprint-oauth.json`:
```json
{
  "client_id": "your-client-id",
  "client_secret": "your-secret",
  "access_token": "your-token"
}
```

### 5. Optional: Set Timezone
```bash
export TZ_OFFSET=12  # e.g., NZST
```

### 6. Bank Files
Create markdown files in `memory/bank/` for persistent knowledge:
- `memory/bank/preferences.md` — user preferences
- `memory/bank/relationships.md` — people and roles
- `memory/bank/experience.md` — lessons learned

These are automatically indexed and included in semantic search.
