# Dashboard Guide

本文档描述当前 `packages/imprint_dashboard/dashboard.py` 的真实页面结构、内嵌前端逻辑和核心交互。Dashboard 是一个单文件 FastAPI 应用：后端 API、HTML、CSS、JavaScript 全部写在同一个 Python 文件中。

---

## 入口和运行方式

Dashboard 入口：

```bash
python3 packages/imprint_dashboard/dashboard.py
```

直接运行时绑定：

```text
http://127.0.0.1:3000
```

`start.sh` 启动 Dashboard 时执行：

```bash
nohup python3 packages/imprint_dashboard/dashboard.py > logs/dashboard.log 2>&1 &
```

systemd 模板 `deploy/imprint-dashboard@.service` 当前执行：

```ini
ExecStart=/usr/bin/python3 packages/imprint_dashboard/dashboard.py
```

Dashboard 读取：

- 项目根目录：`BASE = packages/imprint_dashboard -> project root`
- 数据目录：`IMPRINT_DATA_DIR`，默认 `~/.imprint`
- 数据库：固定读取 `$IMPRINT_DATA_DIR/memory.db`
- 日志目录：项目根目录下 `logs/`

注意：Dashboard 当前不读取 `IMPRINT_DB`。如果核心包通过 `IMPRINT_DB` 指到另一份 SQLite，Dashboard 仍会看 `$IMPRINT_DATA_DIR/memory.db`。

---

## 页面结构

Dashboard 根路由 `GET /` 返回一整段内嵌 HTML。页面主要区域如下：

| 区域 | DOM / 位置 | 数据来源 | 作用 |
|---|---|---|---|
| Header | `Claude Imprint` + language button | `localStorage.imprint-lang` | 语言切换，支持 English / 中文。 |
| Component Cards | `#components` | `/api/status` | 显示 Memory HTTP、Tunnel、Telegram 的运行状态、PID、启停开关。 |
| Info Bar | `#tunnel-url`, `#memory-count`, `#today-logs` | `/api/status` | 显示 tunnel 状态、记忆数量、今日日志行数。 |
| Interaction History | `#heatmap` | `/api/heatmap` | 按日显示 memories、conversation_log、daily log 的互动热力图。 |
| Memory Fragment | `#fragment-text` | `/api/memory-fragment` | 随机展示一条 `importance >= 3` 的记忆片段。 |
| System | `#ns-days`, `#ns-total`, `#ns-today`, `#ns-heartbeat` | `/api/system-status` | 显示活跃天数、总消息数、今日消息数、最近 cron log 时间。 |
| Stream | `#stream-stats` | `/api/stream-stats` | 显示 conversation_log 总量、今日量、平台分布、最新消息。 |
| Scheduled Tasks | `#tasks-list` | `/api/status` | 读取 `~/.claude/scheduled-tasks/*/SKILL.md` frontmatter。 |
| Todos | `#system-todo-content`, `#backlog-display` | `/api/todos/*` | 读取系统待办和 backlog；backlog 可在页面编辑保存。 |
| Horizon | `#stm-section` | `/api/short-term-memory` | 解析 `recent_context.md`，显示跨渠道近期上下文。 |
| Remote Tool Log | `#remote-tools` | `/api/remote-tools` | 显示 `cc_tasks` 最近 20 条远程任务记录。 |
| Summaries | `#summaries-section` | `/api/summaries` | 搜索、编辑、删除 rolling summaries。 |
| Memory | `#memory-section` | `/api/memories`, `/api/decay-status` | 搜索、编辑、删除记忆，并展示情感/衰减元数据。 |
| Live Files | `#live-files` | `/api/live-files` | 展示 CLAUDE.md、recent_context.md、MEMORY.md、daily log、experience、backlog。 |

当前 Dashboard 的 Component Cards 只管理三类组件：

| Key | 命令 | 类型 | 状态检测 |
|---|---|---|---|
| `memory_http` | `memo-clover --http` | background | 优先检测 `:8000` 端口，其次 PID 文件。 |
| `tunnel` | `cloudflared tunnel run my-tunnel` | background | 优先 `pgrep -f "cloudflared tunnel"`，其次 PID 文件。 |
| `telegram` | `claude --permission-mode auto --channels plugin:telegram@claude-plugins-official` | terminal | `pgrep -f "channels plugin:telegram"`。 |

Heartbeat Agent 当前不在 Dashboard 的 `COMPONENTS` 中，不能从页面直接启停；它由 `start.sh` 或 systemd 的 `imprint-heartbeat@.service` 管理。

---

## 后端 API

### 服务控制

| API | 作用 |
|---|---|
| `GET /api/status` | 返回组件状态、tunnel 状态、memory stats、scheduled task 列表。 |
| `POST /api/{component}/start` | 启动 `memory_http`、`tunnel` 或 `telegram`。 |
| `POST /api/{component}/stop` | 停止 `memory_http`、`tunnel` 或 `telegram`。 |
| `GET /api/logs/{component}` | 读取 component 的最近日志。只有配置了 `log_file` 的组件有日志。 |

后台组件启动逻辑：

- 用 `subprocess.Popen()` 启动。
- stdout/stderr 追加到组件配置里的 `log_file`。
- 写 PID 文件到项目根目录。
- `cwd` 为项目根目录。

Terminal 组件启动逻辑：

- 如果存在 `osascript`，认为是 macOS，打开 Terminal 窗口。
- 否则按 Linux 后台进程启动，日志写到 `logs/<component>.log`。

日志按钮只对 `type == "background"` 的组件渲染。当前有真实 `log_file` 的组件是 `memory_http` 和 `tunnel`。

### 数据面 API

| API | 作用 |
|---|---|
| `GET /api/heatmap` | 生成 interaction heatmap。 |
| `GET /api/memories?q=&limit=` | 搜索或列出记忆。 |
| `PUT /api/memories/{memory_id}` | 编辑记忆内容、分类、重要性、情感和衰减元数据。 |
| `DELETE /api/memories/{memory_id}` | 物理删除一条记忆。 |
| `GET /api/decay-status` | 统计 protected、surfacing、resolved、archived、low_score、decaying。 |
| `GET /api/summaries?q=&limit=` | 搜索或列出 rolling summaries。 |
| `PUT /api/summaries/{summary_id}` | 编辑摘要内容、platform、turn_count。 |
| `DELETE /api/summaries/{summary_id}` | 删除摘要。 |
| `GET /api/stream-stats` | conversation_log 统计。 |
| `GET /api/remote-tools` | `cc_tasks` 最近记录。 |
| `GET /api/system-status` | 今日消息、总消息、活跃天数、最近 cron 时间。 |
| `GET /api/memory-fragment` | 随机返回一条 `importance >= 3` 的记忆。 |
| `GET /api/short-term-memory` | 解析 Horizon 使用的 `recent_context.md`。 |
| `GET /api/live-files` | 返回动态文件内容和元信息。 |
| `GET /api/todos/system` | 读取 `system-todos.md`，没有则读 `north-todos.md`。 |
| `GET /api/todos/backlog` | 读取 `backlog.md`。 |
| `PUT /api/todos/backlog` | 保存 `backlog.md`。 |

---

## 前端内嵌逻辑

### 单文件前端

`dashboard()` 直接返回完整 HTML 字符串：

- CSS 写在 `<style>` 中。
- JavaScript 写在 `<script>` 中。
- 没有独立前端构建、打包或静态资源目录。
- 所有页面数据都通过 `fetch()` 调用本地 API 获取。

### i18n

前端内置：

```javascript
const i18n = { en: {...}, zh: {...} }
let lang = localStorage.getItem('imprint-lang') || 'en'
```

点击语言按钮会：

1. 在 `en` 和 `zh` 之间切换。
2. 写入 `localStorage.imprint-lang`。
3. 调用 `refreshAll()` 重新拉取/渲染页面。

`applyStaticI18n()` 会替换标题、placeholder、按钮文案、legend 等静态文本。

### 初始化和轮询

页面加载后立即调用：

```javascript
applyStaticI18n()
fetchStatus()
fetchHeatmap()
fetchSystemStatus()
fetchFragment()
fetchStreamStats()
fetchSummaries()
fetchShortTermMemory()
fetchTodos()
searchMemories()
fetchRemoteTools()
fetchLiveFiles()
```

定时刷新：

| 函数 | 间隔 | 作用 |
|---|---:|---|
| `fetchStatus()` | 3 秒 | 组件状态、info bar、scheduled tasks。 |
| `fetchSystemStatus()` | 10 秒 | System sidebar。 |
| `fetchStreamStats()` | 10 秒 | Stream 统计。 |
| `fetchSummaries()` | 10 秒 | rolling summaries。 |
| `fetchShortTermMemory()` | 5 秒 | Horizon。 |
| `fetchTodos()` | 15 秒 | system tasks / backlog。 |
| `fetchRemoteTools()` | 10 秒 | cc_tasks。 |
| `fetchLiveFiles()` | 10 秒 | Live Files。 |

Memory 列表不会按固定间隔刷新，只在初始化、搜索输入、编辑/删除后刷新。Heatmap 和 Memory Fragment 初始化加载，fragment 可手动刷新。

---

## 核心交互

### 启停组件

前端开关调用：

```text
POST /api/{component}/start
POST /api/{component}/stop
```

成功后 1.5 秒重新调用 `fetchStatus()`。失败时恢复 checkbox 状态并弹窗显示错误。

组件状态展示规则：

- 运行中显示 active dot、`Running`、PID。
- 停止显示 off dot、`Stopped`。
- background 组件显示 Logs 按钮。

### 查看日志

`toggleLog(key)` 调用：

```text
GET /api/logs/{key}
```

后端默认返回最近 30 行。没有 `log_file` 的组件返回 `No logs`；日志文件不存在返回 `Log file not found`。

### 搜索和编辑记忆

Memory 搜索框调用：

```text
GET /api/memories?q=<query>&limit=20
```

后端 `_fetch_memories()` 直接查 SQLite：

- 如果没有 `memory.db`，返回空列表。
- 动态读取 `PRAGMA table_info(memories)`。
- 缺失字段会用 Dashboard 默认值补齐。
- 搜索只做 `content LIKE ?`，不是核心包的 unified search。
- 按 `created_at` 或 `id` 倒序。

编辑记忆时，前端提交：

```json
{
  "content": "...",
  "category": "...",
  "importance": 5,
  "valence": 0.5,
  "arousal": 0.3,
  "resolved": true,
  "pinned": false,
  "decay_rate": "0.05"
}
```

后端处理分两段：

1. `content`、`category`、`importance` 通过 `memo_clover.memory_manager.update_memory()` 更新；如果更新内容，核心包会刷新 embedding。
2. `valence`、`arousal`、`resolved`、`pinned`、`decay_rate` 通过 Dashboard 直接执行 SQLite `UPDATE`，且只在对应列存在时更新。

Dashboard 中的 `activation_count` 和 `last_active` 是兼容字段名。当前核心 schema 使用 `recalled_count` 和 `last_accessed_at`，Dashboard 并没有把它们映射成 `activation_count` / `last_active`，所以在当前库上这两个 badge 可能显示默认值或空值。

删除记忆调用：

```text
DELETE /api/memories/{memory_id}
```

后端调用 `mem.delete_memory()`，这是物理删除，不是归档。

### 摘要管理

Summaries 搜索框调用：

```text
GET /api/summaries?q=<query>&limit=10
```

搜索范围是 `summaries.content` 和 `summaries.platform`。

编辑摘要会更新：

- `content`
- `platform`
- `turn_count`

删除摘要直接删除 `summaries` 表中的行。当前核心 MCP 只有 `save_summary` 和 `get_recent_summaries`，没有 MCP 级 update/delete；Dashboard 的编辑和删除是直接 SQL 实现。

### Horizon

Horizon 读取：

1. `$IMPRINT_DATA_DIR/recent_context.md`
2. 不存在则 fallback 到项目根目录 `recent_context.md`

解析规则：

- HTML 注释跳过。
- `[summary...]` 或 `[摘要...]` 行进入 summaries。
- 其他 `[` 开头行进入 raw messages。
- 返回 `threshold = 120`，前端用它画压缩进度条。

### Todos

System Tasks 读取顺序：

1. `$IMPRINT_DATA_DIR/memory/bank/system-todos.md`
2. `$IMPRINT_DATA_DIR/memory/bank/north-todos.md`

Backlog 读写：

```text
$IMPRINT_DATA_DIR/memory/bank/backlog.md
```

前端只渲染简单 Markdown：

- `##` 小标题
- `- [x]` 已完成
- `- [ ]` 未完成
- `- ` 普通项目

保存 Backlog 时会创建 `memory/bank/` 目录。

### Live Files

Live Files 展示以下文件：

| Key | 路径 |
|---|---|
| `claude_md` | `~/.claude/CLAUDE.md` |
| `recent_context` | `$IMPRINT_DATA_DIR/recent_context.md`，不存在则项目根目录 `recent_context.md` |
| `memory_index` | `$IMPRINT_DATA_DIR/MEMORY.md` |
| `daily_log` | `$IMPRINT_DATA_DIR/memory/YYYY-MM-DD.md` |
| `experience` | `$IMPRINT_DATA_DIR/memory/bank/experience.md` |
| `backlog` | `$IMPRINT_DATA_DIR/memory/bank/backlog.md` |

文件超过 60 分钟未更新时，返回 `stale = true`，前端以 stale 样式显示。

---

## 当前限制

- Dashboard 没有认证层，默认只绑定 `127.0.0.1:3000`。
- Dashboard 不管理 Heartbeat Agent。
- Dashboard 记忆搜索是 SQLite `LIKE`，不是 MCP 的 unified search。
- Dashboard 使用 `$IMPRINT_DATA_DIR/memory.db`，不支持 `IMPRINT_DB` override。
- Dashboard 的 logs API 只读配置了 `log_file` 的组件日志。
- Live Files 和 Horizon 对 `recent_context.md` 有项目根目录 fallback，但大多数数据库相关 API 没有 fallback。

