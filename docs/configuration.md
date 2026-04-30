# Configuration

本文档记录当前代码库实际读取或设置的运行时配置。范围包括：

- `claude-imprint`: 启停脚本、Dashboard、hooks、Heartbeat、Telegram MCP、cron runner、systemd 模板。
- `memo-clover`: 记忆核心包、SQLite 数据库、embedding、HTTP OAuth、message bus、压缩模块。

配置以当前代码为准。PRD 中出现但当前代码没有读取的变量不列为运行时配置。

---

## 配置来源

当前项目没有统一的 `.env` 加载器。

| 场景 | 配置方式 | 备注 |
|---|---|---|
| `./start.sh` | 继承当前 shell 环境变量 | `start.sh` 不读取 `.env`。需要先 `export ...` 再启动。 |
| `./stop.sh` | 基本不依赖环境变量 | 通过 PID 文件和 `pkill` 停进程。 |
| systemd | `deploy/*@.service` 中的 `Environment=...` | 修改 unit 后需要 `systemctl daemon-reload` 并重启服务。 |
| Claude Code hooks | hook 脚本内部设置 | `hooks/post-response.sh` 和 `hooks/pre-compact-flush.sh` 会强制 `export IMPRINT_DATA_DIR="$SCRIPT_DIR"`。 |
| `memo-clover --http` OAuth | `~/.imprint-oauth.json` 优先，其次环境变量 | 如果凭证文件存在，`OAUTH_*` 环境变量会被忽略。 |
| cron runner | shell/PowerShell 环境，加 `~/.claude/cron-token` | 脚本会把 token 文件内容写入 `CLAUDE_CODE_OAUTH_TOKEN`。 |

Python 模块中的环境变量多数在 import 时读取。修改环境变量后，需要重启对应进程才会生效。

---

## 数据目录

### 默认规则

`memo-clover` 的数据库层在 `memo_clover/db.py` 中定义：

| 配置 | 默认值 | 结果 |
|---|---|---|
| `IMPRINT_DATA_DIR` 未设置 | `~/.imprint` | 数据根目录是当前运行用户 home 下的 `.imprint`。 |
| `IMPRINT_DB` 未设置 | `$IMPRINT_DATA_DIR/memory.db` | SQLite 数据库放在数据目录下。 |
| `IMPRINT_DB` 已设置 | 该变量指定的路径 | 只覆盖核心包使用的 SQLite 路径。 |

常见数据文件：

| 路径 | 说明 |
|---|---|
| `$IMPRINT_DATA_DIR/memory.db` | SQLite 主库，核心表和 FTS 索引都在这里。 |
| `$IMPRINT_DATA_DIR/memory.db-wal` / `memory.db-shm` | SQLite WAL 文件，运行中可能出现。 |
| `$IMPRINT_DATA_DIR/MEMORY.md` | 自动生成的记忆索引。 |
| `$IMPRINT_DATA_DIR/memory/YYYY-MM-DD.md` | daily log。 |
| `$IMPRINT_DATA_DIR/memory/bank/*.md` | knowledge bank Markdown 文件。 |
| `$IMPRINT_DATA_DIR/memory/bank/experience.md` | `experience_append` 写入的经验文件。 |
| `$IMPRINT_DATA_DIR/CLAUDE.md` | 关系快照，`build_context()` 会读取。 |

### full-stack 推荐配置

生产或长期运行时，推荐只设置 `IMPRINT_DATA_DIR`，不要额外设置 `IMPRINT_DB`：

```bash
export IMPRINT_DATA_DIR="$HOME/.imprint"
export TZ_OFFSET=0
mkdir -p "$IMPRINT_DATA_DIR"
./start.sh
```

原因：`memo-clover` 核心包支持 `IMPRINT_DB`，但 `claude-imprint` 的 Dashboard、`update_claude_md.py`、Heartbeat 等代码直接读取 `$IMPRINT_DATA_DIR/memory.db`。如果只改 `IMPRINT_DB`，核心服务和 Dashboard 可能看见不同数据库。

### systemd 数据目录

当前 `deploy/` 模板默认使用：

```ini
Environment=IMPRINT_DATA_DIR=/home/%i/.imprint
Environment=TZ_OFFSET=0
```

其中 `%i` 是 systemd template instance 名，通常用用户名启动：

```bash
sudo systemctl enable --now memo-clover@$USER
```

如果要更换数据目录，需要同时修改所有相关 unit，至少包括：

- `deploy/memo-clover@.service`
- `deploy/imprint-dashboard@.service`
- `deploy/imprint-heartbeat@.service`

修改后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart memo-clover@$USER imprint-dashboard@$USER imprint-heartbeat@$USER
```

### hooks 的特殊情况

当前 hooks 不继承外部 `IMPRINT_DATA_DIR`，而是写死为项目根目录：

```bash
export IMPRINT_DATA_DIR="$SCRIPT_DIR"
```

受影响文件：

- `hooks/post-response.sh`
- `hooks/pre-compact-flush.sh`

这意味着 Claude Code hook 写入的数据库默认是：

```text
<claude-imprint repo>/memory.db
```

而 systemd 模板启动的服务默认读取：

```text
/home/<user>/.imprint/memory.db
```

如果希望 hook、HTTP 服务、Dashboard 共用同一份数据库，需要把 hook 脚本中的该行改成同一个目标目录，或接受“项目内 hook 数据”和“服务数据目录”分离的现状。

---

## 环境变量总表

### 核心数据与时间

| 变量 | 默认值 | 必填 | 使用位置 | 作用 |
|---|---:|---|---|---|
| `IMPRINT_DATA_DIR` | `~/.imprint` | 否 | `memo-clover`、Dashboard、Heartbeat、`update_claude_md.py`、hooks | 数据根目录。systemd 模板默认 `/home/%i/.imprint`，hooks 当前强制为项目根目录。 |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | 否 | `memo-clover` 核心包 | 覆盖 SQLite 路径。full-stack 场景不建议单独设置。 |
| `TZ_OFFSET` | `0` | 否 | `memo-clover`、Dashboard、Heartbeat、`update_claude_md.py` | 固定 UTC 小时偏移，例如 `8`、`-4`。代码不处理 IANA 时区或 DST。必须是整数，否则进程导入时会报错。 |

### Embedding 与检索

| 变量 | 默认值 | 必填 | 使用位置 | 作用 |
|---|---:|---|---|---|
| `EMBED_PROVIDER` | `ollama` | 否 | `memo_clover/memory_manager.py` | embedding provider。只有值为 `openai` 时走 OpenAI-compatible API，其他值都会走 Ollama 分支。 |
| `OLLAMA_URL` | `http://localhost:11434` | 否 | `memory_manager.py`、`compress.py`、`console.py`、`hooks/post_response_processor.py` | Ollama API 地址，用于本地 embedding 和摘要压缩。 |
| `OPENAI_API_KEY` | 空字符串 | 仅 `EMBED_PROVIDER=openai` 时需要 | `memory_manager.py`、systemd memory 模板注释 | OpenAI-compatible embedding API 的 bearer token。未设置时 embedding 返回 `None`，检索退化到关键词/FTS 通道。 |
| `EMBED_API_BASE` | `https://api.openai.com` | 否 | `memory_manager.py` | OpenAI-compatible API base，代码会请求 `{EMBED_API_BASE}/v1/embeddings`。 |
| `EMBED_MODEL` | `bge-m3` 或 `text-embedding-3-small` | 否 | `memory_manager.py`、`console.py` | embedding 模型。默认值由 provider 决定：`ollama` 为 `bge-m3`，`openai` 为 `text-embedding-3-small`。 |
| `IMPRINT_BANK_EXCLUDE` | 空字符串 | 否 | `memory_manager.py` | 逗号分隔的 bank 文件名黑名单，例如 `draft.md,private.md`。匹配 `memory/bank/*.md` 的文件名。 |
| `IMPRINT_LOCALE` | `en` | 否 | `memory_manager.py` | `unified_search_text()` 的结果标签语言。当前内置 `en` 和 `zh`。 |

### HTTP OAuth

`memo-clover --http` 会先读取：

```text
~/.imprint-oauth.json
```

文件存在时必须包含：

```json
{
  "client_id": "...",
  "client_secret": "...",
  "access_token": "..."
}
```

可以用当前仓库脚本生成：

```bash
python3 scripts/generate_oauth.py
```

如果 `~/.imprint-oauth.json` 不存在，才会读取以下环境变量：

| 变量 | 默认值 | 必填 | 使用位置 | 作用 |
|---|---:|---|---|---|
| `OAUTH_CLIENT_ID` | 空字符串 | HTTP OAuth 环境变量模式下需要 | `memo_clover/server.py` | OAuth client id。 |
| `OAUTH_CLIENT_SECRET` | 空字符串 | HTTP OAuth 环境变量模式下需要 | `memo_clover/server.py` | OAuth client secret。 |
| `OAUTH_ACCESS_TOKEN` | 空字符串 | 对外暴露 HTTP 服务时需要 | `memo_clover/server.py` | Bearer token。远端请求需要 `Authorization: Bearer <token>`。 |

重要行为：

- 如果 `ACCESS_TOKEN` 为空，HTTP middleware 不强制鉴权，请不要把这种状态暴露到公网 tunnel。
- localhost、`127.0.0.1`、`::1` 请求会绕过 bearer token 检查。
- `~/.imprint-oauth.json` 位于运行用户 home 下，不受 `IMPRINT_DATA_DIR` 影响。

### Telegram 与 Heartbeat

| 变量 | 默认值 | 必填 | 使用位置 | 作用 |
|---|---:|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 空字符串 | 使用 `imprint-telegram` 发送消息/文件时必填 | `packages/imprint_telegram/server.py`、heartbeat systemd 模板注释 | Telegram Bot API token。未设置时工具返回 `Error: TELEGRAM_BOT_TOKEN not configured`。 |
| `TELEGRAM_CHAT_ID` | 空字符串 | 默认聊天目标需要 | `packages/imprint_telegram/server.py`、`packages/imprint_heartbeat/heartbeat.py` | 默认 chat id。工具调用显式传 `chat_id` 时可不设置；Heartbeat 会把它写进 prompt 提示。 |
| `HEARTBEAT_INTERVAL` | `900` | 否 | `packages/imprint_heartbeat/heartbeat.py`、`start.sh` 展示 | Heartbeat 循环间隔，单位秒。 |
| `QUIET_START` | `23` | 否 | `packages/imprint_heartbeat/heartbeat.py` | 安静时段开始小时，按 `TZ_OFFSET` 计算。 |
| `QUIET_END` | `7` | 否 | `packages/imprint_heartbeat/heartbeat.py` | 安静时段结束小时，按 `TZ_OFFSET` 计算。 |

### 压缩、摘要、message bus

| 变量 | 默认值 | 必填 | 使用位置 | 作用 |
|---|---:|---|---|---|
| `COMPRESS_MODEL` | `qwen3:8b` 或 `goekdenizguelmez/JOSIEFIED-Qwen3:8b` | 否 | `memo_clover/compress.py`、`hooks/post_response_processor.py` | 压缩/摘要使用的 Ollama 模型。核心压缩模块默认 `qwen3:8b`，post-response hook 摘要默认 JOSIEFIED 模型。 |
| `COMPRESS_KEEP` | `30` | 否 | `memo_clover/compress.py` | 压缩上下文时保留的最近行数。 |
| `COMPRESS_THRESHOLD` | `50` | 否 | `memo_clover/compress.py` | 触发压缩的 message line 数。 |
| `MESSAGE_BUS_LIMIT` | `40` | 否 | `memo_clover/bus.py` | message bus 保留的最近消息数，写入新消息时自动裁剪。 |

### Cron 与 Claude CLI

| 变量 | 默认值 | 必填 | 使用位置 | 作用 |
|---|---:|---|---|---|
| `IMPRINT_PROJECT_DIR` | `cron-task.sh` 所在目录 | 否 | `cron-task.sh`、`cron-task.ps1` | cron runner 的项目目录覆盖项。 |
| `CLAUDE_CODE_OAUTH_TOKEN` | 无 | Claude CLI OAuth 模式需要 | `cron-task.sh`、`cron-task.ps1` 写入 | cron runner 从 `~/.claude/cron-token` 读取后导出，供 Claude CLI 使用。 |
| `ANTHROPIC_API_KEY` | 无 | Claude CLI API key 模式需要 | deploy README 和 cron 脚本注释 | 当前项目代码不直接读取。用于 Claude CLI 认证，需要按脚本注释手动启用。 |
| `PATH` | 取决于 shell/systemd | 视部署而定 | `deploy/imprint-telegram@.service`、Heartbeat 子进程 | 确保 `claude`、`bun`、`memo-clover` 等命令可执行。Telegram systemd 模板显式设置了 `/home/%i/.local/bin:/usr/local/bin:/usr/bin:/bin`。 |
| `CLAUDECODE` | 继承环境 | 否 | `memo_clover/tasks.py`、Heartbeat 子进程 | 子进程启动 Claude CLI 前会删除该变量，避免嵌套环境污染。不是用户配置项。 |

---

## 非环境变量但必须配置的凭证/文件

| 文件或命令 | 默认位置 | 用途 |
|---|---|---|
| `~/.imprint-oauth.json` | 当前用户 home | `memo-clover --http` OAuth 凭证。优先级高于 `OAUTH_*` 环境变量。 |
| `~/.claude/cron-token` | 当前用户 home | cron runner 读取后写入 `CLAUDE_CODE_OAUTH_TOKEN`。 |
| Cloudflare tunnel 配置 | cloudflared 默认配置目录 | `start.sh` 和 `deploy/imprint-tunnel@.service` 都硬编码执行 `cloudflared tunnel run my-tunnel`。tunnel 名不是环境变量，需要改脚本或 unit。 |
| `.mcp.json` / `cron-mcp*.json` | 项目根目录 | MCP server 命令配置。示例只配置 `memo-clover`，`cron-mcp-full.json` 额外包含 Telegram 和 utils MCP。 |

---

## systemd 模板中的环境变量

当前 `deploy/` 目录提供这些模板：

| Unit | 默认环境变量 |
|---|---|
| `memo-clover@.service` | `IMPRINT_DATA_DIR=/home/%i/.imprint`、`TZ_OFFSET=0`，并注释了 `EMBED_PROVIDER=openai`、`OPENAI_API_KEY=sk-...` |
| `imprint-dashboard@.service` | `IMPRINT_DATA_DIR=/home/%i/.imprint`、`TZ_OFFSET=0` |
| `imprint-heartbeat@.service` | `IMPRINT_DATA_DIR=/home/%i/.imprint`、`TZ_OFFSET=0`、`HEARTBEAT_INTERVAL=900`，并注释了 Telegram token/chat id |
| `imprint-telegram@.service` | `PATH=/home/%i/.local/bin:/usr/local/bin:/usr/bin:/bin` |
| `imprint-tunnel@.service` | 无环境变量 |

模板默认假设：

- 项目路径是 `/home/%i/claude-imprint`。
- `memo-clover` 可执行文件在 `/home/%i/.local/bin/memo-clover`。
- `claude` 可执行文件在 `/home/%i/.local/bin/claude`。
- `cloudflared` 可执行文件在 `/usr/local/bin/cloudflared`。

如果服务安装在虚拟环境中，需要修改 `ExecStart`，例如：

```ini
ExecStart=/home/%i/claude-imprint/.venv/bin/memo-clover --http
```

---

## 当前没有实现的变量

以下名称出现在 PRD 或历史说明中，但当前运行时代码没有读取：

| 名称 | 当前状态 |
|---|---|
| `LLM_API_KEY` | 当前代码未读取。 |
| `MEMORY_SECRET` | 当前代码未读取。HTTP 鉴权使用 `~/.imprint-oauth.json` 或 `OAUTH_*`。 |
| `IMPRINT_LAT` / `IMPRINT_LON` | 只在 skill 文档示例中提到，当前代码未读取。 |

