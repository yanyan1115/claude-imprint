# Claude Imprint

**English | [中文](#中文)**

Claude Imprint is a self-hosted long-term memory system for Claude. It connects Claude Code, Claude.ai, Telegram, and other entry points to the same memory store, so conversations, summaries, task state, and cross-channel context can be saved, searched, and reused over time.

This repository is built on **MemoClover** (Python package name `memo-clover` / `memo_clover`). On top of the standalone Claude long-term memory core, it adds a Dashboard, multi-channel messaging, automation tasks, Telegram notifications, Cloudflare Tunnel access, and deployment templates.

## What You Can Do With It

- Share one memory store between Claude Code and Claude.ai.
- View memories, summaries, short-term context, runtime status, and interaction heatmaps in the Dashboard.
- Write Telegram conversations into the unified memory store, then retrieve them from Claude.ai / Claude Code.
- Use cron / heartbeat jobs for scheduled reminders, health checks, morning briefings, and automatic cleanup.
- Store long-term knowledge, relationship snapshots, and conversation logs with SQLite + FTS5 + optional vector retrieval.

## Quick Start: Docker

This path is best for a first trial. The goal is to start Memory HTTP and the Dashboard within 15 minutes.

### 1. Clone The Project

```bash
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint
```

### 2. Prepare Environment Variables

```bash
cp .env.example .env
```

Open `.env` and at least confirm these values:

```env
IMPRINT_DATA_DIR=~/.imprint
TZ_OFFSET=0
MEMORY_HTTP_PORT=8000
DASHBOARD_PORT=3000
```

Telegram, LLM, Cloudflare, and other variables can stay empty at first. Fill them in when you enable the corresponding modules.

### 3. Start Core Services

```bash
docker compose up -d memory-http dashboard
```

Open the Dashboard:

```text
http://localhost:3000
```

Memory HTTP listens by default at:

```text
http://localhost:8000/mcp
```

Check status:

```bash
docker compose ps
docker compose logs -f dashboard
```

Run the one-command smoke test:

```bash
bash scripts/smoke_test.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

### 4. Optional: Start A Local Vector Model

If you want local vector retrieval:

```bash
docker compose --profile vector up -d ollama
docker exec -it claude-imprint-ollama ollama pull bge-m3
```

Then set `OLLAMA_URL` in `.env`:

```env
OLLAMA_URL=http://ollama:11434
```

Restart the services:

```bash
docker compose restart memory-http dashboard
```

### 5. Optional: Expose Temporarily To Claude.ai

Start a Cloudflare quick tunnel:

```bash
docker compose --profile tunnel up cloudflared
```

Copy the `trycloudflare.com` URL from the logs, then add the Memory HTTP MCP address as a Custom Connector in Claude.ai.

For the complete Claude.ai integration flow, see [docs/tutorial-01-memory.md](docs/tutorial-01-memory.md) and [docs/deployment-runbook.md](docs/deployment-runbook.md).

## Quick Start: Local Python

Use this path if you want to run on the host machine, or if you need Claude Code / Telegram channel integration:

```bash
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
export IMPRINT_DATA_DIR="$HOME/.imprint"
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
$env:IMPRINT_DATA_DIR="$HOME\.imprint"
```

Start Memory HTTP:

```bash
memo-clover --http
```

Open another terminal and start the Dashboard:

```bash
python packages/imprint_dashboard/dashboard.py
```

Open:

```text
http://localhost:3000
```

## Connect Claude Code

Register the memory MCP:

```bash
claude mcp add -s user memo-clover -- memo-clover
```

Install hooks so conversations automatically enter the memory pipeline:

```bash
claude settings add-hook PreCompact "bash $(pwd)/hooks/pre-compact-flush.sh"
claude settings add-hook Stop "bash $(pwd)/hooks/post-response.sh"
```

For more about hooks and automation, see [docs/hooks-and-automation.md](docs/hooks-and-automation.md).

## Connect Claude.ai

Minimal flow:

1. Start `memo-clover --http`.
2. Expose `localhost:8000` with Cloudflare Tunnel.
3. Add a Custom Connector in Claude.ai Settings -> Connectors.
4. Verify by calling the memory search / remember tools in Claude.ai.

For the detailed tutorial, see [docs/tutorial-01-memory.md](docs/tutorial-01-memory.md).

## Connect Telegram

Telegram has two paths:

- Official Claude Code Telegram channel plugin: handles two-way chat with Claude in Telegram.
- `packages/imprint_telegram/server.py`: lets Claude / cron / heartbeat proactively send Telegram messages.

Start the channel quickly:

```bash
claude /telegram:configure
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

For full configuration, BotFather token setup, `TELEGRAM_CHAT_ID`, write verification, and retrieval verification, see [packages/imprint_telegram/README.md](packages/imprint_telegram/README.md).

## Key Configuration

See the complete template in [.env.example](.env.example).

| Variable | Description |
| --- | --- |
| `IMPRINT_DATA_DIR` | Unified data directory. All services must use the same value. |
| `IMPRINT_DB` | Optional SQLite path. Defaults to `$IMPRINT_DATA_DIR/memory.db`. |
| `TZ_OFFSET` | Timezone offset in hours. |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible LLM configuration; use `LLM_BASE_URL=https://api.deepseek.com` and `LLM_MODEL=deepseek-v4-flash` for DeepSeek V4 Flash. |
| `EMBED_PROVIDER` / `EMBED_API_BASE` / `EMBED_MODEL` | MemoClover vector retrieval configuration; set `EMBED_PROVIDER=openai`, `EMBED_API_BASE=https://api.deepseek.com`, and `EMBED_MODEL=deepseek-v4-flash` for a DeepSeek-compatible endpoint. |
| `EMBED_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` | API key for OpenAI-compatible embedding providers. `EMBED_API_KEY` is preferred; the others are compatibility aliases. |
| `OLLAMA_URL` | Local Ollama endpoint. |
| `DECAY_LAMBDA` / `DECAY_THRESHOLD` | Emotional decay parameters. |
| `AROUSAL_SURFACING_THRESHOLD` | Proactive resurfacing threshold. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram Bot API sending configuration. |

DeepSeek V4 Flash example:

```bash
export LLM_BASE_URL=https://api.deepseek.com
export LLM_API_KEY=sk-...
export LLM_MODEL=deepseek-v4-flash

export EMBED_PROVIDER=openai
export EMBED_API_BASE=https://api.deepseek.com
export EMBED_API_KEY=sk-...
export EMBED_MODEL=deepseek-v4-flash
```

The Dashboard memory panel now supports paginated loading and clickable status chips. Click a chip such as `protected`, `low score`, or `decaying` to filter the list; click it again or click `total` to return to all memories.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/tutorial-01-memory.md](docs/tutorial-01-memory.md) | Connect Claude.ai Custom Connector from scratch. |
| [packages/imprint_telegram/README.md](packages/imprint_telegram/README.md) | Telegram BotFather, channel, sending tools, write verification, and retrieval verification. |
| [docs/dashboard-guide.md](docs/dashboard-guide.md) | Dashboard API and page guide. |
| [docs/configuration.md](docs/configuration.md) | Configuration items, path strategy, and environment variables. |
| [docs/prd-schema-gap.md](docs/prd-schema-gap.md) | Gap list between the PRD entity/relationship model and the current schema. |
| [docs/deployment-runbook.md](docs/deployment-runbook.md) | Linux / systemd / Cloudflare / troubleshooting. |
| [docs/database-schema.md](docs/database-schema.md) | SQLite schema and table structure. |
| [docs/memory-lifecycle.md](docs/memory-lifecycle.md) | Memory write, summary, decay, and retrieval lifecycle. |
| [docs/hooks-and-automation.md](docs/hooks-and-automation.md) | hooks, cron, and heartbeat automation. |

## Directory Overview

```text
packages/imprint_dashboard/   Dashboard
packages/imprint_telegram/    Telegram Bot API MCP
packages/imprint_utils/       system_status / webpage / Spotify tools
hooks/                        Claude Code hooks
cron-prompts/                 Scheduled-task prompt templates
deploy/                       systemd service templates
docs/                         Architecture, API, deployment, and tutorial docs
examples/                     Examples such as CLAUDE.md
```

## Production Deployment

For Linux servers, systemd templates are recommended:

```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now memo-clover@$USER
sudo systemctl enable --now imprint-dashboard@$USER
sudo systemctl enable --now imprint-telegram@$USER
```

For deployment details, see [deploy/README.md](deploy/README.md) and [docs/deployment-runbook.md](docs/deployment-runbook.md).

## Security Notes

- Do not commit a real `.env`.
- Do not expose `TELEGRAM_BOT_TOKEN`, Cloudflare tokens, or OAuth credentials.
- `IMPRINT_DATA_DIR` may contain private memories, conversations, relationship snapshots, and logs.
- Before open-sourcing, check `data/`, `memories/`, `logs/`, and `.claude/` for personal data.

## Credits

- [MemoClover](https://github.com/Qizhan7/MemoClover)
- [Anthropic Claude Code](https://docs.anthropic.com/)
- OpenAI ChatGPT Codex
- Google Gemini
- [Ollama](https://ollama.com)
- [bge-m3](https://huggingface.co/BAAI/bge-m3)

## License

[MIT](LICENSE)

---

<a id="中文"></a>

# Claude Imprint

**[English](#claude-imprint) | 中文**

Claude Imprint 是一个自托管的 Claude 长期记忆系统：它把 Claude Code、Claude.ai、Telegram 等入口接到同一份记忆库里，让对话、摘要、任务状态和跨渠道上下文可以持续保存、检索和复用。

本仓库基于 **MemoClover**（Python 包名 `memo-clover` / `memo_clover`），在独立的 Claude 长期记忆核心驱动之上补充 Dashboard、多渠道消息、自动化任务、Telegram 通知、Cloudflare Tunnel 接入和部署模板。

## 你能用它做什么

- 在 Claude Code 和 Claude.ai 之间共享同一份记忆。
- 通过 Dashboard 查看记忆、摘要、短期上下文、运行状态和交互热力图。
- 把 Telegram 对话写入统一记忆库，并从 Claude.ai / Claude Code 检索出来。
- 用 cron / heartbeat 做定时提醒、健康检查、晨间简报和自动整理。
- 用 SQLite + FTS5 + 可选向量检索保存长期知识、关系快照和对话日志。

## 快速开始：Docker

适合第一次体验，目标是在 15 分钟内启动 Memory HTTP 和 Dashboard。

### 1. 克隆项目

```bash
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint
```

### 2. 准备环境变量

```bash
cp .env.example .env
```

打开 `.env`，至少确认这些值：

```env
IMPRINT_DATA_DIR=~/.imprint
TZ_OFFSET=0
MEMORY_HTTP_PORT=8000
DASHBOARD_PORT=3000
```

Telegram、LLM、Cloudflare 等变量可以先留空，等对应模块启用时再填。

### 3. 启动核心服务

```bash
docker compose up -d memory-http dashboard
```

打开 Dashboard：

```text
http://localhost:3000
```

Memory HTTP 默认监听：

```text
http://localhost:8000/mcp
```

查看状态：

```bash
docker compose ps
docker compose logs -f dashboard
```

一键自检：

```bash
bash scripts/smoke_test.sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

### 4. 可选：启动本地向量模型

如果你想启用本地向量检索：

```bash
docker compose --profile vector up -d ollama
docker exec -it claude-imprint-ollama ollama pull bge-m3
```

然后把 `.env` 中的 `OLLAMA_URL` 设置为：

```env
OLLAMA_URL=http://ollama:11434
```

重启服务：

```bash
docker compose restart memory-http dashboard
```

### 5. 可选：临时暴露给 Claude.ai

启动 Cloudflare quick tunnel：

```bash
docker compose --profile tunnel up cloudflared
```

从日志中复制 `trycloudflare.com` URL，然后到 Claude.ai 的 Custom Connector 中添加 Memory HTTP MCP 地址。

更完整的 Claude.ai 接入流程见 [docs/tutorial-01-memory.md](docs/tutorial-01-memory.md) 和 [docs/deployment-runbook.md](docs/deployment-runbook.md)。

## 快速开始：本地 Python

如果你想在宿主机上运行，或需要接入 Claude Code / Telegram channel：

```bash
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
export IMPRINT_DATA_DIR="$HOME/.imprint"
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
$env:IMPRINT_DATA_DIR="$HOME\.imprint"
```

启动 Memory HTTP：

```bash
memo-clover --http
```

另开一个终端启动 Dashboard：

```bash
python packages/imprint_dashboard/dashboard.py
```

打开：

```text
http://localhost:3000
```

## 接入 Claude Code

注册记忆 MCP：

```bash
claude mcp add -s user memo-clover -- memo-clover
```

安装 hooks，让对话自动进入记忆链路：

```bash
claude settings add-hook PreCompact "bash $(pwd)/hooks/pre-compact-flush.sh"
claude settings add-hook Stop "bash $(pwd)/hooks/post-response.sh"
```

更多 hooks 与自动化说明见 [docs/hooks-and-automation.md](docs/hooks-and-automation.md)。

## 接入 Claude.ai

最小流程：

1. 启动 `memo-clover --http`。
2. 用 Cloudflare Tunnel 暴露 `localhost:8000`。
3. 在 Claude.ai Settings -> Connectors 添加 Custom Connector。
4. 在 Claude.ai 中调用 memory search / remember 工具验证。

详细教程见 [docs/tutorial-01-memory.md](docs/tutorial-01-memory.md)。

## 接入 Telegram

Telegram 有两条链路：

- 官方 Claude Code Telegram channel plugin：负责在 Telegram 里和 Claude 双向聊天。
- `packages/imprint_telegram/server.py`：负责让 Claude / cron / heartbeat 主动发送 Telegram 消息。

快速启动 channel：

```bash
claude /telegram:configure
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

完整配置、BotFather token、`TELEGRAM_CHAT_ID`、入库验证和检索验证见 [packages/imprint_telegram/README.md](packages/imprint_telegram/README.md)。

## 关键配置

完整模板见 [.env.example](.env.example)。

| 变量 | 说明 |
| --- | --- |
| `IMPRINT_DATA_DIR` | 统一数据目录，所有服务必须一致。 |
| `IMPRINT_DB` | 可选 SQLite 路径，默认 `$IMPRINT_DATA_DIR/memory.db`。 |
| `TZ_OFFSET` | 时区偏移小时数。 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible LLM 配置；DeepSeek V4 Flash 使用 `LLM_BASE_URL=https://api.deepseek.com` 和 `LLM_MODEL=deepseek-v4-flash`。 |
| `EMBED_PROVIDER` / `EMBED_API_BASE` / `EMBED_MODEL` | MemoClover 向量检索配置；DeepSeek-compatible endpoint 使用 `EMBED_PROVIDER=openai`、`EMBED_API_BASE=https://api.deepseek.com`、`EMBED_MODEL=deepseek-v4-flash`。 |
| `EMBED_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` | OpenAI-compatible embedding provider 的 API key。优先使用 `EMBED_API_KEY`，其余为兼容别名。 |
| `OLLAMA_URL` | 本地 Ollama 地址。 |
| `DECAY_LAMBDA` / `DECAY_THRESHOLD` | 情感衰减参数。 |
| `AROUSAL_SURFACING_THRESHOLD` | 主动浮现阈值。 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram Bot API 发送配置。 |

DeepSeek V4 Flash 示例：

```bash
export LLM_BASE_URL=https://api.deepseek.com
export LLM_API_KEY=sk-...
export LLM_MODEL=deepseek-v4-flash

export EMBED_PROVIDER=openai
export EMBED_API_BASE=https://api.deepseek.com
export EMBED_API_KEY=sk-...
export EMBED_MODEL=deepseek-v4-flash
```

Dashboard 记忆面板现在支持分页加载和可点击状态标签。点击 `已保护`、`低分`、`衰减中` 等标签会过滤列表并高亮当前视图；再次点击当前标签或点击 `总数` 会恢复显示全部。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [docs/tutorial-01-memory.md](docs/tutorial-01-memory.md) | 从零接入 Claude.ai Custom Connector。 |
| [packages/imprint_telegram/README.md](packages/imprint_telegram/README.md) | Telegram BotFather、channel、发送工具、入库与检索验证。 |
| [docs/dashboard-guide.md](docs/dashboard-guide.md) | Dashboard API 与页面说明。 |
| [docs/configuration.md](docs/configuration.md) | 配置项、路径策略、环境变量。 |
| [docs/prd-schema-gap.md](docs/prd-schema-gap.md) | PRD 实体/关系模型与当前 schema 的差异清单。 |
| [docs/deployment-runbook.md](docs/deployment-runbook.md) | Linux / systemd / Cloudflare / 排障。 |
| [docs/database-schema.md](docs/database-schema.md) | SQLite schema 与表结构。 |
| [docs/memory-lifecycle.md](docs/memory-lifecycle.md) | 记忆写入、摘要、衰减、检索生命周期。 |
| [docs/hooks-and-automation.md](docs/hooks-and-automation.md) | hooks、cron、heartbeat 自动化。 |

## 目录速览

```text
packages/imprint_dashboard/   Dashboard
packages/imprint_telegram/    Telegram Bot API MCP
packages/imprint_utils/       system_status / webpage / Spotify tools
hooks/                        Claude Code hooks
cron-prompts/                 定时任务 prompt 模板
deploy/                       systemd 服务模板
docs/                         架构、API、部署、教程文档
examples/                     CLAUDE.md 等示例
```

## 生产部署

Linux 服务器推荐使用 systemd 模板：

```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now memo-clover@$USER
sudo systemctl enable --now imprint-dashboard@$USER
sudo systemctl enable --now imprint-telegram@$USER
```

部署细节见 [deploy/README.md](deploy/README.md) 和 [docs/deployment-runbook.md](docs/deployment-runbook.md)。

## 安全提醒

- 不要提交真实 `.env`。
- 不要公开 `TELEGRAM_BOT_TOKEN`、Cloudflare token、OAuth credentials。
- `IMPRINT_DATA_DIR` 中可能包含私人记忆、对话、关系快照和日志。
- 开源前请检查 `data/`、`memories/`、`logs/`、`.claude/` 是否包含个人数据。

## 致谢

- [MemoClover](https://github.com/Qizhan7/MemoClover)
- [Anthropic Claude Code](https://docs.anthropic.com/)
- OpenAI ChatGPT Codex
- Google Gemini
- [Ollama](https://ollama.com)
- [bge-m3](https://huggingface.co/BAAI/bge-m3)

## License

[MIT](LICENSE)
