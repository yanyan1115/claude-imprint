#!/usr/bin/env python3
"""
imprint-wechat — MCP Server
Send and read WeChat messages via iLink Bot API.

Usage:
  python3 server.py    # stdio mode

Requires: WeChat channel running + context_token from recent user message.
Bot account stored in ~/.wechat-claude/accounts/*.json
"""

import json
import sys
import uuid
import base64
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("imprint-wechat")

ACCOUNTS_DIR = Path.home() / ".wechat-claude" / "accounts"
TOKEN_FILE = Path.home() / ".wechat-claude" / "context-tokens.json"
INBOX_FILE = Path.home() / ".wechat-claude" / "inbox.json"


def _load_account():
    """Load bot account info."""
    account_files = list(ACCOUNTS_DIR.glob("*.json")) if ACCOUNTS_DIR.exists() else []
    if not account_files:
        return None
    with open(account_files[0]) as f:
        return json.load(f)


def _load_context_token():
    """Load context token for messaging."""
    if not TOKEN_FILE.exists():
        return None, None
    with open(TOKEN_FILE) as f:
        tokens = json.load(f)
    if not tokens:
        return None, None
    user_id = list(tokens.keys())[0]
    return user_id, tokens[user_id]["token"]


@mcp.tool()
def send_wechat(text: str) -> str:
    """Send a WeChat message via iLink Bot. Requires the WeChat channel to be running
    and a valid context_token (the user must have sent a message recently)."""
    account = _load_account()
    if not account:
        return "Error: No WeChat bot account found. Start the WeChat channel and scan QR first."

    base_url = account.get("baseUrl", "https://ilinkai.weixin.qq.com")
    bot_token = account.get("token", "")

    user_id, context_token = _load_context_token()
    if not context_token:
        return "Error: No context_token. The user needs to send a WeChat message first."

    body = json.dumps({
        "msg": {
            "from_user_id": "",
            "to_user_id": user_id,
            "client_id": f"wechat-claude-{uuid.uuid4().hex[:8]}",
            "message_type": 2,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
            "context_token": context_token,
        },
        "base_info": {"channel_version": "1.0.0"},
    }).encode()

    uin = base64.b64encode(uuid.uuid4().bytes).decode()
    url = f"{base_url}/ilink/bot/sendmessage"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("AuthorizationType", "ilink_bot_token")
    req.add_header("Authorization", f"Bearer {bot_token}")
    req.add_header("X-WECHAT-UIN", uin)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            err_code = result.get("errcode", result.get("err_code", 0))
            if err_code == 0:
                return "WeChat message sent"
            return f"Error: iLink API: {json.dumps(result, ensure_ascii=False)}"
    except Exception as e:
        return f"Error: Send failed: {str(e)}"


@mcp.tool()
def read_wechat(limit: int = 10) -> str:
    """Read recent WeChat inbox messages. Returns the last N messages received from the user.
    limit: number of messages to return, default 10, max 50."""
    if not INBOX_FILE.exists():
        return "Inbox empty (WeChat channel not running or no messages received yet)"

    try:
        with open(INBOX_FILE) as f:
            inbox = json.load(f)
    except Exception:
        return "Error: Failed to read inbox"

    if not inbox:
        return "Inbox empty"

    limit = min(max(1, limit), 50)
    recent = inbox[-limit:]

    lines = []
    for msg in recent:
        ts = msg.get("ts", "?")[:19].replace("T", " ")
        text = msg.get("text", "")
        lines.append(f"[{ts}] {text}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
