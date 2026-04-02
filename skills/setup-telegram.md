---
name: setup-telegram
description: Guide through setting up Telegram integration
triggers:
  - setup telegram
  - configure telegram
  - connect telegram
---

# Setup Telegram Integration

Guide the user through connecting Telegram to Claude Imprint.

## Prerequisites
- A Telegram account
- BotFather to create a bot

## Steps

### 1. Create a Telegram Bot
Tell the user:
1. Open Telegram and message @BotFather
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

### 2. Get Chat ID
Tell the user:
1. Start a conversation with their new bot
2. Send any message to the bot
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser
4. Find `"chat":{"id":XXXXXXX}` — that's the chat_id

### 3. Configure Environment
Help the user set environment variables. Create or update the file:
`~/.claude/channels/telegram/.env`

```
TELEGRAM_BOT_TOKEN=<the token from step 1>
TELEGRAM_CHAT_ID=<the chat_id from step 2>
```

### 4. Register MCP Server
Add to the project's `.mcp.json`:
```json
{
  "mcpServers": {
    "imprint-telegram": {
      "command": "python3",
      "args": ["packages/imprint_telegram/server.py"]
    }
  }
}
```

### 5. Test
Use `send_telegram` with a test message to verify it works.

### 6. Optional: Telegram Channel Plugin
For two-way chat (receiving messages from user), also set up the official Telegram channel plugin:
```bash
claude --channels plugin:telegram@claude-plugins-official
```
