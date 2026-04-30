# imprint-telegram 使用指南

`imprint-telegram` 是 Claude Imprint 的 Telegram 接入组件之一，用来让 Claude 通过 Telegram Bot API 主动发送消息和文件。

需要先分清两条链路：

| 能力 | 组件 | 作用 |
| --- | --- | --- |
| 在 Telegram 里和 Claude 对话 | Claude Code 官方 Telegram channel plugin | 接收 Telegram 消息，并把消息送进 Claude Code。 |
| 把 Telegram 对话写入记忆库 | Claude Imprint hooks | 读取 Claude Code transcript，写入 `conversation_log`，并刷新 `recent_context.md`。 |
| 让 Claude / cron / heartbeat 主动发 Telegram | `imprint-telegram` MCP | 调用 Telegram Bot API，提供 `send_telegram` 等工具。 |

也就是说：双向聊天依赖官方 Telegram channel plugin；本目录里的 `imprint-telegram` 主要负责“主动发消息”。

## 1. 前置条件

开始前，请先确认核心服务已经能跑起来：

1. 已安装 Python 3.11+。
2. 已安装并登录 Claude Code CLI。
3. 已安装 Claude Imprint 依赖。
4. Memory HTTP 可以启动：

   ```bash
   imprint-memory --http
   ```

5. Dashboard 可以访问：

   ```text
   http://localhost:3000
   ```

6. 所有服务使用同一个数据目录：

   ```bash
   export IMPRINT_DATA_DIR="$HOME/.imprint"
   ```

Windows PowerShell：

```powershell
$env:IMPRINT_DATA_DIR="$HOME\.imprint"
```

## 2. 用 BotFather 创建 Telegram Bot

在 Telegram 搜索：

```text
@BotFather
```

打开官方 BotFather 后点击 **Start**，发送：

```text
/newbot
```

按提示填写：

| 项目 | 示例 | 说明 |
| --- | --- | --- |
| Bot 显示名称 | `My Imprint Memory` | 显示在 Telegram 里的名字。 |
| Bot username | `my_imprint_memory_bot` | 必须全网唯一，通常以 `bot` 结尾。 |

创建成功后，BotFather 会返回一个 token，例如：

```text
1234567890:AAExampleExampleExampleExample
```

这个 token 等同于 bot 密钥。不要提交到 GitHub，不要贴到公开聊天，不要出现在截图里。

## 3. 获取 Telegram Chat ID

`imprint-telegram` 主动发消息时需要知道发给谁，这个目标就是 `TELEGRAM_CHAT_ID`。

推荐方法：

1. 在 Telegram 搜索 `@userinfobot`。
2. 点击 **Start**。
3. 复制它返回的数字 `Id`。

也可以先给自己的 bot 发一条消息，然后在浏览器打开：

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

在返回 JSON 里找：

```json
"chat":{"id":123456789}
```

这个数字就是 `TELEGRAM_CHAT_ID`。

## 4. 配置环境变量

本地测试可以直接在 shell 里设置：

```bash
export IMPRINT_DATA_DIR="$HOME/.imprint"
export TELEGRAM_BOT_TOKEN="1234567890:AAExampleExampleExampleExample"
export TELEGRAM_CHAT_ID="123456789"
```

Windows PowerShell：

```powershell
$env:IMPRINT_DATA_DIR="$HOME\.imprint"
$env:TELEGRAM_BOT_TOKEN="1234567890:AAExampleExampleExampleExample"
$env:TELEGRAM_CHAT_ID="123456789"
```

部署时推荐写入 `.env` 或 systemd environment：

```env
IMPRINT_DATA_DIR=/home/your-user/.imprint
TELEGRAM_BOT_TOKEN=1234567890:AAExampleExampleExampleExample
TELEGRAM_CHAT_ID=123456789
TZ_OFFSET=8
```

| 变量 | 必填 | 用途 |
| --- | --- | --- |
| `IMPRINT_DATA_DIR` | 是 | 统一的数据目录，Memory / Dashboard / hooks / Telegram 服务必须一致。 |
| `TELEGRAM_BOT_TOKEN` | 主动发送必填 | BotFather 返回的 Bot API token。 |
| `TELEGRAM_CHAT_ID` | 默认接收人必填 | `send_telegram` 未显式传 `chat_id` 时使用。 |
| `TZ_OFFSET` | 可选 | Dashboard 与日志日期偏移，例如 UTC+8 填 `8`。 |
| `PATH` | 部署相关 | systemd 下要能找到 `claude`、`python3`、`bun`、`imprint-memory` 等命令。 |

## 5. 配置 Telegram 双向聊天

这一步负责“你在 Telegram 里发消息给 Claude”。

先运行官方配置流程：

```bash
claude /telegram:configure
```

按提示填入 BotFather token。

然后启动 Telegram channel：

```bash
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

保持这个进程运行。Linux 服务器上建议用 systemd；本地测试时保持终端窗口打开即可。

## 6. 配置 imprint-telegram MCP 发送工具

本目录提供两个 MCP 工具：

| 工具 | 作用 |
| --- | --- |
| `send_telegram(text, chat_id="")` | 发送 Telegram 文本消息。 |
| `send_telegram_photo(file_path, caption="", chat_id="")` | 发送本地图片或文件。 |

MCP 配置示例：

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

仓库根目录已有 `cron-mcp-full.json`，其中包含：

- `imprint-memory`
- `imprint-telegram`
- `imprint-utils`

如果 cron / heartbeat 任务需要发 Telegram 通知，优先使用这个完整 MCP 配置。

## 7. 启动方式

### 本地测试

启动 Telegram channel：

```bash
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

另开一个终端启动 Dashboard：

```bash
python packages/imprint_dashboard/dashboard.py
```

打开：

```text
http://localhost:3000
```

Telegram channel 正常运行时，Dashboard 的 Telegram 组件卡片应显示为 running。

### 使用项目启动脚本

Linux / macOS：

```bash
./start.sh
```

脚本会尝试启动 Memory HTTP、Dashboard 和 Telegram。若当前机器没有 `claude` CLI，会跳过 Telegram。

### Linux systemd

使用 `deploy/imprint-telegram@.service` 后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now imprint-telegram@$USER
sudo systemctl status imprint-telegram@$USER --no-pager
```

查看日志：

```bash
journalctl -u imprint-telegram@$USER -f
```

模板中已设置：

```ini
Environment=IMPRINT_DATA_DIR=/home/%i/.imprint
Environment=PATH=/home/%i/.local/bin:/usr/local/bin:/usr/bin:/bin
```

如果你的仓库目录或数据目录不同，请先修改 service 文件。

### Windows PowerShell

本地测试：

```powershell
$env:IMPRINT_DATA_DIR="$HOME\.imprint"
$env:TELEGRAM_BOT_TOKEN="1234567890:AAExampleExampleExampleExample"
$env:TELEGRAM_CHAT_ID="123456789"
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

测试期间保持 PowerShell 窗口打开。

## 8. 验证主动发送是否成功

让 Claude 或 MCP 客户端调用：

```text
send_telegram("Hello from Claude Imprint.")
```

预期返回：

```text
Message sent to Telegram
```

如果返回：

```text
Error: TELEGRAM_BOT_TOKEN not configured
```

说明启动 MCP server 的环境里没有设置 `TELEGRAM_BOT_TOKEN`。

如果返回：

```text
Error: No chat_id specified and TELEGRAM_CHAT_ID not set
```

说明没有设置 `TELEGRAM_CHAT_ID`，也没有在工具调用里显式传入 `chat_id`。

## 9. 验证 Telegram 消息是否进入记忆库

给自己的 Telegram bot 发送一条容易检索的测试消息：

```text
请记住：我的 Telegram 测试暗号是 blue lemon 0429。
```

等 Claude 收到并回复后，从下面几个位置检查。

### Dashboard

打开：

```text
http://localhost:3000
```

检查：

- Telegram 组件显示 running。
- Stream / Horizon 里出现 Telegram 活动。
- Short-term Memory 更新。
- Live Files 中的 `recent_context.md` 有新内容。

### recent_context.md

Linux / macOS：

```bash
cat "$IMPRINT_DATA_DIR/recent_context.md"
```

Windows PowerShell：

```powershell
Get-Content "$env:IMPRINT_DATA_DIR\recent_context.md"
```

预期能看到与 `blue lemon 0429` 相关的 Telegram 记录或摘要。

### SQLite conversation_log

Linux / macOS：

```bash
sqlite3 "$IMPRINT_DATA_DIR/memory.db" \
  "SELECT platform, direction, content, created_at FROM conversation_log ORDER BY id DESC LIMIT 5;"
```

Windows PowerShell：

```powershell
sqlite3 "$env:IMPRINT_DATA_DIR\memory.db" "SELECT platform, direction, content, created_at FROM conversation_log ORDER BY id DESC LIMIT 5;"
```

预期最近记录里有 `platform=telegram`。

## 10. 验证 Telegram 记忆是否可检索

发送一条唯一测试内容：

```text
请记住：我的 Telegram 检索验证码是 coral-window-7301。
```

然后任选一种方式验证。

### Dashboard 搜索

在 Dashboard 的记忆搜索里输入：

```text
coral-window-7301
```

预期可以看到 Telegram 来源的消息或提取后的记忆。

### Claude.ai Custom Connector

对 Claude 说：

```text
帮我搜索一下我刚才在 Telegram 里提到的检索验证码。
```

预期 Claude 调用 memory search，并返回 `coral-window-7301`。

### Claude Code

在本地 Claude Code 会话里问：

```text
请从记忆库里查找 Telegram 检索验证码。
```

如果当前会话已配置 `imprint-memory` MCP，预期可以检索到 Telegram 端写入的记忆。

## 11. 数据流说明

Telegram 接收链路：

```text
Telegram
  -> 官方 Claude Code Telegram channel plugin
  -> Claude Code transcript JSONL
  -> hooks/post_response_processor.py
  -> conversation_log
  -> recent_context.md
  -> Dashboard / 上下文注入 / 检索链路
```

Telegram 主动发送链路：

```text
Claude / cron / heartbeat
  -> imprint-telegram MCP
  -> Telegram Bot API
  -> Telegram chat
```

最常见的问题是数据目录不一致。请确保 Memory HTTP、Dashboard、hooks、cron、heartbeat、Telegram service 使用同一个 `IMPRINT_DATA_DIR`。

## 12. 常见问题

### Bot 没有收到消息

检查：

- 是否已经运行 `claude /telegram:configure`。
- Telegram channel 进程是否还在运行。
- Bot token 是否正确。
- 是否已经在 Telegram 里对 bot 发送 `/start`。
- 当前网络是否能访问 Telegram。

### Dashboard 里 Telegram 显示 stopped

Linux / macOS 检查：

```bash
pgrep -af "channels plugin:telegram"
```

Windows 检查是否仍有终端在运行：

```powershell
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

新版 Dashboard 已使用跨平台 `psutil` 探测，正常运行的 Telegram channel 应显示为 running。

### Dashboard 看不到 Telegram 消息

先检查数据目录：

```bash
echo "$IMPRINT_DATA_DIR"
```

再检查数据库：

```bash
sqlite3 "$IMPRINT_DATA_DIR/memory.db" "SELECT platform, content FROM conversation_log ORDER BY id DESC LIMIT 5;"
```

如果数据库有 Telegram 记录但 Dashboard 不显示，重启 Dashboard 并刷新页面。

### recent_context.md 为空

可能原因：

- Telegram channel 还没有处理过消息。
- post-response hook 没有安装或没有触发。
- Telegram 进程写入了另一个 `IMPRINT_DATA_DIR`。
- 当前 Telegram 会话收到消息后还没有产生 Claude 回复。

### Token 泄露怎么办

1. 打开 `@BotFather`。
2. 对对应 bot 使用 `/revoke`。
3. 复制新 token。
4. 更新 `TELEGRAM_BOT_TOKEN`。
5. 重启相关服务。

## 13. 安全建议

- 不要提交 `.env`。
- 不要公开 `TELEGRAM_BOT_TOKEN`。
- 个人记忆 bot 建议只自己使用。
- 不建议把个人记忆 bot 拉进公开群。
- 服务器上的 `.env` 或 systemd environment 文件应限制访问权限。
- token 泄露后立刻轮换。

## 14. 下一步

Telegram 跑通后，可以继续：

1. 启动 Memory HTTP，并用 Cloudflare Tunnel 暴露给 Claude.ai。
2. 在 Claude.ai 添加 Custom Connector。
3. 验证 Telegram 写入的记忆能从 Claude.ai 检索出来。
4. 在服务器上启用 `imprint-telegram@$USER` 和 heartbeat。
5. 确保所有 runtime surface 都使用同一个 `IMPRINT_DATA_DIR`。
