---
name: setup-wechat
description: Guide through setting up WeChat integration via iLink Bot
triggers:
  - setup wechat
  - configure wechat
  - connect wechat
---

# Setup WeChat Integration

Guide the user through connecting WeChat to Claude Imprint via iLink Bot.

## Prerequisites
- A WeChat account
- Node.js and npm installed
- The `claude-wechat-channel` npm package

## Steps

### 1. Install WeChat Channel
```bash
npm install -g claude-wechat-channel
```

### 2. Start WeChat Channel
```bash
claude --permission-mode auto --dangerously-load-development-channels server:wechat
```
This will show a QR code. Scan it with your WeChat app to log in.

### 3. Send a Message
After scanning, send any message from your WeChat to the bot. This establishes the `context_token` needed for outbound messaging.

Account info is stored in `~/.wechat-claude/accounts/`.
Context tokens are stored in `~/.wechat-claude/context-tokens.json`.

### 4. Register MCP Server
Add to the project's `.mcp.json`:
```json
{
  "mcpServers": {
    "imprint-wechat": {
      "command": "python3",
      "args": ["packages/imprint_wechat/server.py"]
    }
  }
}
```

### 5. Test
Use `send_wechat` with a test message to verify it works.

## Notes
- The WeChat channel uses iLink Bot API
- Context tokens expire if no messages are sent for a while
- If you get red exclamation marks, wait 1-2 minutes (rate limiting) and try again
- You do NOT need to re-scan QR code for temporary rate limits
