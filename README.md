# Claude Imprint

Claude Imprint 是一个自托管的 Claude 长期记忆系统：它把 Claude Code、Claude.ai、Telegram 等入口接到同一份记忆库里，让对话、摘要、任务状态和跨渠道上下文可以持续保存、检索和复用。

本仓库基于 `imprint-memory`，在持久记忆之上补充 Dashboard、多渠道消息、自动化任务、Telegram 通知、Cloudflare Tunnel 接入和部署模板。

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
imprint-memory --http
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
claude mcp add -s user imprint-memory -- imprint-memory
```

安装 hooks，让对话自动进入记忆链路：

```bash
claude settings add-hook PreCompact "bash $(pwd)/hooks/pre-compact-flush.sh"
claude settings add-hook Stop "bash $(pwd)/hooks/post-response.sh"
```

更多 hooks 与自动化说明见 [docs/hooks-and-automation.md](docs/hooks-and-automation.md)。

## 接入 Claude.ai

最小流程：

1. 启动 `imprint-memory --http`。
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
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible LLM 配置。 |
| `OLLAMA_URL` | 本地 Ollama 地址。 |
| `DECAY_LAMBDA` / `DECAY_THRESHOLD` | 情感衰减参数。 |
| `AROUSAL_SURFACING_THRESHOLD` | 主动浮现阈值。 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram Bot API 发送配置。 |

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
sudo systemctl enable --now imprint-memory@$USER
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

- [imprint-memory](https://github.com/Qizhan7/imprint-memory)
- [Anthropic Claude Code](https://docs.anthropic.com/)
- [Ollama](https://ollama.com)
- [bge-m3](https://huggingface.co/BAAI/bge-m3)

## License

[MIT](LICENSE)
