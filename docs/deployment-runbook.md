# Deployment Runbook

本文档是一份面向运维的启停和排障手册，按当前 `claude-imprint` 与 `imprint-memory` 代码实际行为编写。

---

## 运行组件

| 组件 | 启动命令 | 端口 | 日志 |
|---|---|---:|---|
| Memory HTTP | `imprint-memory --http` | `8000` | `logs/http.log` 或 systemd journal |
| Dashboard | `python3 packages/imprint_dashboard/dashboard.py` | `3000` | `logs/dashboard.log` 或 systemd journal |
| Cloudflare Tunnel | `cloudflared tunnel run my-tunnel` | n/a | `logs/tunnel.log` 或 systemd journal |
| Telegram Channel | `claude --permission-mode auto --channels plugin:telegram@claude-plugins-official` | n/a | Linux: `logs/telegram.log`; macOS: Terminal 窗口 |
| Heartbeat Agent | `python3 -u packages/imprint_heartbeat/agent.py` | n/a | `logs/agent.log` 或 systemd journal |

---

## 快速启停：start.sh / stop.sh

### 启动

```bash
cd ~/claude-imprint
source .venv/bin/activate  # 如果 imprint-memory 安装在虚拟环境中

export IMPRINT_DATA_DIR="$HOME/.imprint"
export TZ_OFFSET=0

./start.sh
```

`start.sh` 会按顺序尝试启动：

1. `imprint-memory --http`
2. `cloudflared tunnel run my-tunnel`
3. Claude Telegram channel
4. Heartbeat Agent
5. Dashboard

脚本行为：

- 自动 `cd` 到项目根目录。
- 自动创建 `logs/`。
- 不读取 `.env`，只继承当前 shell 环境变量。
- 如果 `cloudflared` 不存在，会跳过 tunnel。
- 如果 `claude` CLI 不存在，会跳过 Telegram channel。
- macOS 下 Telegram 会打开 Terminal 窗口；Linux 下会后台运行并写 PID 文件。
- macOS 且存在 `caffeinate` 时，Heartbeat 会通过 `caffeinate -i` 防止睡眠。

启动后的本地入口：

```text
Dashboard:  http://localhost:3000
Memory API: http://localhost:8000/mcp
```

### PID 文件

`start.sh` 在项目根目录写入：

| 文件 | 组件 |
|---|---|
| `.pid-http` | Memory HTTP |
| `.pid-tunnel` | Cloudflare Tunnel |
| `.pid-telegram` | Linux Telegram channel |
| `.pid-heartbeat` | Heartbeat Agent |
| `.pid-dashboard` | Dashboard |

### 停止

```bash
cd ~/claude-imprint
./stop.sh
```

`stop.sh` 会：

- 读取上述 PID 文件并发送 `kill`。
- 删除已处理的 PID 文件。
- 额外执行 `pkill -f "imprint-memory --http"`。
- 额外执行 `pkill -f "cloudflared tunnel"`。
- Linux 下额外执行 `pkill -f "channels plugin:telegram"`。
- macOS 下提示手动关闭 Telegram Terminal 窗口。

注意：`stop.sh` 没有额外 `pkill` Dashboard orphan。若 Dashboard PID 文件丢失但进程仍在，可手动处理：

```bash
pkill -f "imprint_dashboard/dashboard.py"
```

---

## systemd 部署

### 安装依赖和代码

```bash
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果使用自维护的 `imprint-memory` fork：

```bash
pip install git+https://github.com/yanyan1115/imprint-memory.git --force-reinstall --no-deps
```

### 检查模板路径

当前模板默认：

| 项 | 默认值 |
|---|---|
| `WorkingDirectory` | `/home/%i/claude-imprint` |
| Memory `ExecStart` | `/home/%i/.local/bin/imprint-memory --http` |
| Dashboard `ExecStart` | `/usr/bin/python3 packages/imprint_dashboard/dashboard.py` |
| Heartbeat `ExecStart` | `/usr/bin/python3 -u packages/imprint_heartbeat/agent.py` |
| Telegram `ExecStart` | `/home/%i/.local/bin/claude --permission-mode auto --channels plugin:telegram@claude-plugins-official` |
| Tunnel `ExecStart` | `/usr/local/bin/cloudflared tunnel run my-tunnel` |

如果服务安装在 `.venv` 中，需要先修改模板，例如：

```ini
ExecStart=/home/%i/claude-imprint/.venv/bin/imprint-memory --http
```

Dashboard 和 Heartbeat 若需要虚拟环境中的依赖，也应改成 `.venv/bin/python`：

```ini
ExecStart=/home/%i/claude-imprint/.venv/bin/python packages/imprint_dashboard/dashboard.py
ExecStart=/home/%i/claude-imprint/.venv/bin/python -u packages/imprint_heartbeat/agent.py
```

### 配置环境变量

至少确认这些 unit 中的数据目录一致：

```ini
Environment=IMPRINT_DATA_DIR=/home/%i/.imprint
Environment=TZ_OFFSET=0
```

涉及文件：

- `deploy/imprint-memory@.service`
- `deploy/imprint-dashboard@.service`
- `deploy/imprint-heartbeat@.service`

如果服务器没有 Ollama，Memory unit 可改用 OpenAI-compatible embedding：

```ini
Environment=EMBED_PROVIDER=openai
Environment=OPENAI_API_KEY=sk-...
Environment=EMBED_API_BASE=https://api.openai.com
Environment=EMBED_MODEL=text-embedding-3-small
```

如果 Heartbeat 需要直接使用 `imprint-telegram` MCP 发送 Telegram：

```ini
Environment=TELEGRAM_BOT_TOKEN=...
Environment=TELEGRAM_CHAT_ID=...
```

### 安装 unit

```bash
sudo cp deploy/*@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 启动和开机自启

建议先启动 Memory，再启动依赖它的组件：

```bash
sudo systemctl enable --now imprint-memory@$USER
sudo systemctl enable --now imprint-dashboard@$USER
sudo systemctl enable --now imprint-heartbeat@$USER
```

按需启动：

```bash
sudo systemctl enable --now imprint-tunnel@$USER
sudo systemctl enable --now imprint-telegram@$USER
```

### 查看状态

```bash
sudo systemctl status imprint-memory@$USER --no-pager
sudo systemctl status imprint-dashboard@$USER --no-pager
sudo systemctl status imprint-heartbeat@$USER --no-pager
```

### 重启

```bash
sudo systemctl restart imprint-memory@$USER
sudo systemctl restart imprint-dashboard@$USER
sudo systemctl restart imprint-heartbeat@$USER
```

### 停止和取消开机启动

```bash
sudo systemctl disable --now imprint-memory@$USER
sudo systemctl disable --now imprint-dashboard@$USER
sudo systemctl disable --now imprint-heartbeat@$USER
sudo systemctl disable --now imprint-tunnel@$USER
sudo systemctl disable --now imprint-telegram@$USER
```

---

## 日志

### start.sh 模式

项目根目录下的 `logs/`：

| 文件 | 来源 |
|---|---|
| `logs/http.log` | `imprint-memory --http` stdout/stderr |
| `logs/tunnel.log` | `cloudflared tunnel run my-tunnel` stdout/stderr |
| `logs/telegram.log` | Linux Telegram channel stdout/stderr |
| `logs/agent.log` | Heartbeat Agent stdout/stderr |
| `logs/dashboard.log` | Dashboard stdout/stderr |
| `logs/post-response.log` | Claude Code post-response hook |
| `logs/compaction.log` | PreCompact hook |
| `logs/compress.log` | post-response hook 触发的后台压缩 |
| `logs/cron-<task>.log` | `cron-task.sh` / `cron-task.ps1` |
| `logs/.offset-*` | post-response hook 的 transcript byte offset marker |
| `logs/.catchup-*` | post-response hook 的 catch-up marker |

查看实时日志：

```bash
tail -f logs/http.log
tail -f logs/dashboard.log
tail -f logs/agent.log
tail -f logs/tunnel.log
```

Dashboard 也提供 `/api/logs/{component}`，但当前只对配置了 `log_file` 的 component 返回真实日志：

- `memory_http`
- `tunnel`

`telegram` 在 Dashboard component 配置中没有 `log_file`，该接口会返回 `No logs`。

### systemd 模式

systemd unit 默认没有写入项目 `logs/*.log`，stdout/stderr 进入 journal。

查看日志：

```bash
journalctl -u imprint-memory@$USER -f
journalctl -u imprint-dashboard@$USER -f
journalctl -u imprint-heartbeat@$USER -f
journalctl -u imprint-tunnel@$USER -f
journalctl -u imprint-telegram@$USER -f
```

查看最近 200 行：

```bash
journalctl -u imprint-memory@$USER -n 200 --no-pager
```

---

## 健康检查

### 进程和端口

```bash
pgrep -af "imprint-memory --http"
pgrep -af "imprint_dashboard/dashboard.py"
pgrep -af "cloudflared tunnel"
pgrep -af "channels plugin:telegram"
pgrep -af "imprint_heartbeat/agent.py"
```

端口：

```bash
lsof -i :8000
lsof -i :3000
```

HTTP：

```bash
curl -i http://localhost:8000/mcp
curl -i http://localhost:3000/api/status
```

### imprint-console

如果安装了 `imprint-memory` console script：

```bash
imprint-console --status
```

它会检查：

- `memory.db` 是否存在。
- 核心表计数。
- Ollama 是否可用。
- HTTP server 是否响应 `localhost:8000/mcp`。

---

## 常见故障处理

### Memory HTTP 没有启动

症状：

- `http://localhost:8000/mcp` 不通。
- `logs/http.log` 或 journal 中有 `command not found`、import error、端口占用。

处理：

```bash
which imprint-memory
imprint-memory --http
```

如果使用虚拟环境：

```bash
source ~/claude-imprint/.venv/bin/activate
which imprint-memory
```

systemd 模式下，确认 `ExecStart` 指向真实可执行文件，然后：

```bash
sudo systemctl daemon-reload
sudo systemctl restart imprint-memory@$USER
journalctl -u imprint-memory@$USER -n 100 --no-pager
```

### Dashboard 显示空数据

最常见原因是数据目录不一致。

检查服务环境：

```bash
systemctl show imprint-memory@$USER -p Environment
systemctl show imprint-dashboard@$USER -p Environment
```

检查数据库位置：

```bash
ls -lah ~/.imprint/memory.db
ls -lah ~/claude-imprint/memory.db
```

当前 hooks 会把 `IMPRINT_DATA_DIR` 设置为项目根目录，而 systemd 模板使用 `/home/%i/.imprint`。如果两边都在写数据，就会出现 Dashboard 和 hook 数据不一致。

### 端口被占用

```bash
lsof -i :8000
lsof -i :3000
```

终止旧进程：

```bash
pkill -f "imprint-memory --http"
pkill -f "imprint_dashboard/dashboard.py"
```

然后重启：

```bash
./start.sh
```

或：

```bash
sudo systemctl restart imprint-memory@$USER imprint-dashboard@$USER
```

### OAuth 或 Claude.ai connector 连接失败

确认 HTTP 服务启动：

```bash
curl -i http://localhost:8000/mcp
```

确认 OAuth 凭证存在：

```bash
ls -lah ~/.imprint-oauth.json
```

如果不存在，生成：

```bash
python3 scripts/generate_oauth.py
```

注意：

- `~/.imprint-oauth.json` 优先于 `OAUTH_CLIENT_ID`、`OAUTH_CLIENT_SECRET`、`OAUTH_ACCESS_TOKEN`。
- 如果 `access_token` 为空，HTTP middleware 不强制鉴权，不应暴露到公网。
- 更新 Claude.ai connector 配置后，通常需要断开并重连 connector。

### Cloudflare Tunnel 没有启动

`start.sh` 会在找不到 `cloudflared` 时跳过 tunnel。

检查：

```bash
which cloudflared
cloudflared tunnel list
cloudflared tunnel run my-tunnel
```

当前脚本和 systemd 模板都硬编码 tunnel 名为 `my-tunnel`。如果实际 tunnel 名不同，需要修改：

- `start.sh`
- `deploy/imprint-tunnel@.service`
- Dashboard 中的 tunnel start command 位于 `packages/imprint_dashboard/dashboard.py`

### Telegram 不能发送

如果是 `imprint-telegram` MCP 工具报错：

```text
Error: TELEGRAM_BOT_TOKEN not configured
Error: No chat_id specified and TELEGRAM_CHAT_ID not set
```

设置：

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```

systemd Heartbeat 需要写进 `deploy/imprint-heartbeat@.service`。直接启动 Telegram channel 还需要 `claude` CLI 和官方 plugin：

```bash
which claude
claude --permission-mode auto --channels plugin:telegram@claude-plugins-official
```

### Heartbeat 没有动作

检查日志：

```bash
tail -f logs/agent.log
```

或：

```bash
journalctl -u imprint-heartbeat@$USER -f
```

常见原因：

- `claude` CLI 不在 `PATH`。
- `~/.claude/CLAUDE.md` 不存在或内容为空。
- `HEARTBEAT_INTERVAL` 设置过大。
- 当前时间落在 `QUIET_START` 到 `QUIET_END`，Heartbeat prompt 会要求非紧急不发消息。
- Claude CLI 子进程 300 秒超时。

### Embedding 不工作但搜索仍有结果

当前代码允许 embedding 失败，检索会退化到 FTS5/LIKE。

Ollama 模式检查：

```bash
curl http://localhost:11434/api/tags
```

OpenAI-compatible 模式检查：

```bash
export EMBED_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export EMBED_API_BASE=https://api.openai.com
export EMBED_MODEL=text-embedding-3-small
```

切换 provider 后建议重建 embedding：

```bash
imprint-memory
# 在 MCP 中调用 memory_reindex
```

或通过可用的客户端调用 `memory_reindex` 工具。

### SQLite FTS5 或 bank_chunks 索引异常

症状：

- `memory_search` 对明显存在的中文、英文或中英混合内容返回空结果。
- `conversation_search` 返回空结果，但 `conversation_log` 中能直接看到对应记录。
- 日志中出现 `database disk image is malformed`、`no such table: memories_fts`、`no such table: conversation_log_fts`、`malformed MATCH expression` 等 SQLite/FTS 错误。
- `$IMPRINT_DATA_DIR/memory/bank/*.md` 中有内容，但搜索不到对应知识库条目。

恢复步骤：

1. 停止写入进程，避免恢复期间继续写库。

   ```bash
   pkill -f "imprint-memory --http"
   pkill -f "imprint_dashboard/dashboard.py"
   ```

2. 备份数据库和 WAL 文件。

   ```bash
   cd "$IMPRINT_DATA_DIR"
   cp memory.db "memory.db.backup.$(date +%Y%m%d-%H%M%S)"
   cp memory.db-wal "memory.db-wal.backup.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
   cp memory.db-shm "memory.db-shm.backup.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
   ```

3. 重启 `imprint-memory`，通过 MCP 调用 `memory_reindex`。

   该工具会输出每个目标的状态：`memory_vectors`、`memories_fts`、`conversation_log_fts`、`bank_chunks`。

4. 验证回归查询。

   ```text
   memory_search("SQLite")
   memory_search("检索")
   memory_search("SQLite FTS5 检索")
   conversation_search("telegram")
   ```

5. 如果 `memory_reindex` 仍失败，保留备份文件和完整输出，再检查是否是主表损坏。FTS 表和 `bank_chunks` 都是派生索引；`memories`、`conversation_log`、`memory/bank/*.md` 才是恢复的权威来源。

### SQLite database is locked

核心连接设置了 WAL 和 busy timeout，但长时间写入或多进程错配仍可能造成锁等待。

处理：

```bash
pkill -f "imprint-memory --http"
pkill -f "imprint_dashboard/dashboard.py"
./start.sh
```

systemd：

```bash
sudo systemctl restart imprint-memory@$USER imprint-dashboard@$USER
```

同时确认没有两套服务分别写不同目录中的数据库，或同一数据库被旧进程长期占用。

### Retrieval Evaluation / Tuning Runbook

检索调参必须先跑固定评估夹具，再调整参数。当前夹具位于核心包仓库：

```powershell
cd D:\APP\imprint-memory
python -m pytest tests/test_retrieval_eval.py -q
```

完整核心包回归：

```powershell
cd D:\APP\imprint-memory
python -m pytest -q
```

主框架集成回归需要指向本地核心包：

```powershell
cd D:\APP\claude-imprint\claude-imprint
$env:PYTHONPATH='D:\APP\imprint-memory'
python -m pytest -q
```

当前 evaluation fixtures 锁定的行为：

- 中英混合精确命中优先：`SQLite FTS5 检索` 不应被弱语义噪声压过。
- 低相似度向量会在进入 RRF 前被 `VEC_PRE_FILTER` 拦截。
- 没有 FTS 命中但向量相似度足够高时，vector-only memory 可以浮现。
- Bank pool 能稳定返回 Markdown chunk。
- Conversation pool 能稳定返回 `conversation_log` 命中。

调参顺序：

1. 先新增或更新 evaluation fixture，描述要保护的查询和预期排序。
2. 跑 `tests/test_retrieval_eval.py`，确认当前基线是否真的暴露问题。
3. 只改一个参数或一个 rerank 因素。
4. 同时跑核心包全量测试和主框架集成测试。
5. 如果排序变化合理，再把调参原因记录到 PR/提交说明或本 runbook。

主要参数和风险：

| 参数 | 当前值 | 作用 | 调整风险 |
|---|---:|---|---|
| `VEC_PRE_FILTER` | `0.3` | memory / bank 向量候选进入 RRF 前的最低相似度。 | 调低会让弱相关向量污染排序；调高会漏掉只有语义相关、没有关键词命中的结果。 |
| `RRF_K` | `60` | Reciprocal Rank Fusion 的平滑常量。 | 调小会放大头部名次差异；调大会让多通道弱命中更接近，排序变化不直观。 |
| `MIN_FINAL_SCORE` | `0.003` | rerank 后的最低保留分。 | 调高可能误删单通道好结果；调低会放进更多噪声。 |
| `RERANK_BLEND` | `0.3` | time / activation / importance / emotion 对 RRF 分数的影响比例。 | 调高会让业务权重压过相关性；调低会削弱时效和情绪浮现。 |
| `LIKE_LIMIT` | `50` | 每个 pool 的 LIKE 兜底候选数量。 | 调高会增加成本和噪声；调低可能漏掉精确 substring 兜底。 |

经验原则：

- 精确关键词和 FTS 命中应优先保护。
- vector-only 结果必须通过明确相似度门槛。
- 情绪和时间 rerank 是二级排序因素，不应压过明显更相关内容。
- bank 和 conversation 的 pool 覆盖要单独验证，避免只看 memory pool。

---

## 服务器更新流程参考

如果只更新 `imprint-memory` 包，当前服务器流程可以是：

```bash
cd ~/claude-imprint
source .venv/bin/activate
pip install git+https://github.com/yanyan1115/imprint-memory.git --force-reinstall --no-deps
pkill -f "imprint-memory --http"
imprint-memory --http &
```

如果使用 systemd，推荐改为：

```bash
cd ~/claude-imprint
source .venv/bin/activate
pip install git+https://github.com/yanyan1115/imprint-memory.git --force-reinstall --no-deps
sudo systemctl restart imprint-memory@$USER
journalctl -u imprint-memory@$USER -n 100 --no-pager
```

如果新增或修改 MCP tool，Claude.ai connector 侧通常需要断开并重连，才能重新发现工具。
