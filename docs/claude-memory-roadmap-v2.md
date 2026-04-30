# 搭建路线图：Claude 长期记忆库系统

**配套文档：** claude-memory-prd-v2.md  
**版本：** v0.3（Phase 4 文档对齐 + Phase 5 P0 核心重构归档）  
**预计总工时：** 约 1 周（原 2-3 周，省掉从零搭基础设施的部分）  
**工具：** Cursor（写代码）+ 云服务器 + 朋友协助环境配置  
**底座：** Claude Imprint（已实现 MCP Server + Cloudflare Tunnel + Dashboard）  
**情感衰减：** 移植自 Ombre-Brain（改进版艾宾浩斯遗忘曲线 + Russell 情感坐标）

---

## 当前进度归档（2026-04-29）

### Phase 4：全局架构与文档对齐（已完成）

今天已完成 Claude Imprint / imprint-memory 的架构文档、API 文档、配置文档、Dashboard 文档、数据库 schema 文档、部署 runbook、hooks 自动化文档、memory lifecycle 文档的系统性梳理与对齐，并已提交归档。

完成内容：
- 明确 `IMPRINT_DATA_DIR` / `IMPRINT_DB` / OAuth / systemd / hooks 的配置边界。
- 补齐 Dashboard API、MCP tools、数据库表、hooks 自动化、memory lifecycle 的真实实现说明。
- 将 Phase 2 / Phase 3 的情感字段、衰减机制、surfacing、bank index、conversation log 等实现状态写入文档。
- 将文档中的已知差异显式标出，为 Phase 5 P0 修复提供依据。

### Phase 5：P0 级核心重构（已完成）

今天已完成并推送三个 P0 修复：

1. `compress_context` 漂移修复
   - `scripts/compress_context.py` 改为调用核心包的 `compress_file()`。
   - `imprint_memory.compress` 补 `compress_context()` 兼容别名。
   - wrapper 只有在核心包不可导入时才走 tail fallback。

2. `IMPRINT_DATA_DIR` 路径策略统一
   - hooks / cron 统一为：优先读取环境变量，未配置则 fallback 到 `$HOME/.imprint`。
   - `recent_context.md` 主写入路径迁移到 `$IMPRINT_DATA_DIR/recent_context.md`。
   - Dashboard / `update_claude_md.py` 保留项目根 fallback，用于旧数据迁移兼容。
   - `imprint-telegram@.service` 补齐 `IMPRINT_DATA_DIR=/home/%i/.imprint`。

3. MCP Summary 能力对齐
   - `memory_manager.py` 新增 `update_summary()` / `delete_summary()`，Summary 写入规则下沉到核心层。
   - `server.py` 新增 MCP tools：`update_summary`、`delete_summary`。
   - Dashboard Summary PUT/DELETE 改为调用 `memory_manager`，不再直连 SQL。
   - 补充 `save -> update -> delete` 生命周期测试。

Runtime 冒烟测试结果：
- Memory HTTP 可在 `localhost:8000` 启动。
- Dashboard 可在 `localhost:3000` 启动。
- `/api/status`、`/api/summaries`、`/api/short-term-memory` 可返回 JSON。
- Summary 核心层、MCP tool 层、Dashboard HTTP PUT/DELETE 均通过真实调用测试。
- `compress_context.py` 已确认进入 `imprint_memory.compress` 链路；本机未运行 Ollama 时会按核心包逻辑降级保留最近消息。
- Windows 本地环境下 Dashboard 的进程状态探测会显示 `memory_http.running=false`，原因是当前状态检测依赖 `lsof` / `pgrep`，属于后续跨平台兼容任务，不影响服务实际监听。

---

## 变更说明（对比 v0.1）

原 Roadmap 的核心工作量在"从零搭基础设施"——FastAPI、PostgreSQL、pgvector、MCP 协议层、接入 claude.ai，这五块加起来占了 2-3 周预估工时里的大半。

换底座之后，Claude Imprint 已经把这些全部做完了。调整后的 Roadmap 重心从"搭"变成"改"和"验"：

| 原计划 | 新计划 | 节省 |
|--------|--------|------|
| Phase 0 买服务器 | 保留（仍需买服务器） | — |
| Phase 1 从零搭 FastAPI + PostgreSQL | **删除**，Imprint 替代 | ~3-5 天 |
| Phase 2 加向量检索 + 分层 | **大幅缩短**，只补情感字段 + 衰减逻辑 | ~2-3 天 |
| Phase 3 网关层 | **大幅缩短**，验证已有能力 + 补关系快照 | ~4-6 天 |
| Phase 3.3 写 MCP 工具接口 | **删除**，Imprint 已有 | ~2 天 |
| Phase 4 接入 claude.ai | **变成配置任务**，不是开发任务 | ~1-2 天 |
| Phase 5 管理面板 + 开源打包 | 保留，在 Imprint 基础上封装 | — |
| 新增 Phase 6 | 移植 Ombre-Brain 情感衰减设计 | 新增 ~1-2 天 |

---

## Phase 0：准备工作（正式动手前）

**目标：** 把所有前置条件准备好，避免做到一半卡住。

### 0.1 买服务器
- 腾讯云或阿里云轻量应用服务器
- 配置：2核2G，40GB 硬盘，Ubuntu 22.04
- 建议请有经验的朋友帮忙确认配置和初始化（SSH 登录、开防火墙端口）

### 0.2 准备 Cloudflare 账号
- 注册免费 Cloudflare 账号
- 下载安装 cloudflared（Cloudflare Tunnel 客户端）
- 不需要自己买域名，Cloudflare Tunnel 会分配免费子域名

### 0.3 准备 API Key
- 注册 DeepSeek 或阿里云，申请 API Key（用于记忆提取，推荐 deepseek-chat 或 qwen-turbo，成本极低）
- 备选：任何支持 OpenAI 兼容格式的 API 都行

### 0.4 本地环境
- 安装 Docker Desktop（本地测试用）
- 安装 Cursor
- 把 PRD 文档放进项目文件夹，Cursor 打开

### 0.5 Fork Claude Imprint
- 在 GitHub 上 fork Claude Imprint 仓库
- 阅读其 README，确认 Module A（HTTP MCP Server + Cloudflare Tunnel）的部署路径

**完成标志：** SSH 能登上服务器，Cloudflare 账号激活，API Key 拿到手，Imprint 仓库 fork 完成。

---

## Phase 1：跑通 Claude Imprint（约 1 天）

**目标：** 按 Imprint 原版教程走一遍，在 claude.ai 里验证记忆工具能正常调用。这是整个项目最重要的一步——不先跑通就不要往后走。

### 1.1 部署 Imprint 到服务器
```bash
git clone https://github.com/your-fork/claude-imprint
cd claude-imprint
cp .env.example .env
# 填写 API Key 等配置
docker compose up -d
```

### 1.2 配置 Cloudflare Tunnel
- 按 Imprint 的 Module A 教程，把 memory_mcp.py 的 HTTP 端口通过 Cloudflare Tunnel 暴露到公网
- 拿到类似 `https://xxx.trycloudflare.com` 的地址

### 1.3 在 claude.ai 添加 Custom Connector
- claude.ai → Settings → Integrations → Add Custom Connector
- 填写 Tunnel 地址和鉴权密钥
- 验证：让 Claude 调用 memory_search，能返回结果

### 1.4 基础功能验收
- 手动存一条记忆（通过面板或 API）
- 在 claude.ai 聊天，确认 Claude 能读到这条记忆
- 确认 memory_remember / memory_search / memory_forget / memory_list 四个工具都跑通
- 确认 Dashboard 可以正常访问

**完成标志：** claude.ai 里的 Claude 能调用 memory_search 并读到记忆。这一步跑通了，后面的工作都是在这个基础上加功能。

---

## Phase 2：补强检索层（约 1-2 天）

**目标：** 在 Imprint 已有的 FTS5 + bge-m3 向量检索基础上，加入情感权重维度，让 PRD 要求的四维混合检索完整落地。

### 2.1 给 memories 表加情感字段

在 Imprint 的数据库 schema 里新增字段：

```sql
ALTER TABLE memories ADD COLUMN valence REAL DEFAULT 0.5;
ALTER TABLE memories ADD COLUMN arousal REAL DEFAULT 0.3;
ALTER TABLE memories ADD COLUMN resolved BOOLEAN DEFAULT 0;
ALTER TABLE memories ADD COLUMN activation_count INTEGER DEFAULT 1;
ALTER TABLE memories ADD COLUMN last_active DATETIME;
```

### 2.2 修改记忆提取 prompt

在调用 LLM 提取记忆的 prompt 里，新增打标要求：
- 让 LLM 同时输出 valence（0.0-1.0）和 arousal（0.0-1.0）两个值
- 提示示例：`"valence: 情感效价，0=非常负面，1=非常正面；arousal: 唤醒度，0=平静，1=激动"`

### 2.3 在 memory_manager.py 里调整检索权重

把当前的检索逻辑改为四维加权：
```python
score = (
    vector_score   * 0.6 +   # bge-m3 语义相似度（已有）
    fts_score      * 0.2 +   # FTS5 关键词匹配（已有）
    time_score     * 0.1 +   # 时间衰减（已有）
    arousal_score  * 0.1     # 情感权重（新增）
)
```
加最低相似度门槛：向量相似度 < 0.6 的直接过滤。

**完成标志：** 存一条带强烈情感的记忆（如某次约定），搜索时它的排名明显高于情感平淡的记忆。

---

## Phase 3：情感衰减引擎（约 1-2 天）

**目标：** 移植 Ombre-Brain 的 decay_engine.py，让记忆有自然遗忘机制——情感丰富的记忆衰减更慢，重要但未解决的记忆会主动浮现。

### 3.1 移植 decay_engine.py

把 Ombre-Brain 的 `decay_engine.py` 复制进项目，调整以下参数对应 PRD 分层：

```python
# 在 decay 配置里按 category 设置 decay_rate
decay_rates = {
    "core_profile": 0.0,   # L1，永不衰减
    "task_state":   0.02,  # L2，数周衰减
    "episode":      0.05,  # L3，数月衰减
    "atomic":       0.10,  # L4，按衰减
}
```

核心公式不变（直接复用 Ombre-Brain）：
```
Score = importance × (activation_count ^ 0.3) × e^(-λ × days) × (base + arousal × boost)
```

### 3.2 实现主动浮现机制

在 `context_builder.py` 里加一个浮现逻辑：

```python
# 查询 resolved=False 且 arousal > 0.7 的记忆
surfaced = get_surfaced_memories(threshold=0.7)
# 这些记忆排在注入顺序的最前面，权重 ×1.5
```

### 3.3 接入 decay 后台任务

在服务启动时起一个后台任务，每 24 小时跑一次 decay cycle：
- 扫描所有动态记忆，算 Score
- Score < 0.3 的自动归档（不删除，但不再主动推送）
- 归档的记忆仍可通过关键词被唤醒

**完成标志：** 手动创建一条过期很久的记忆，设 last_active 为 90 天前，decay cycle 跑完后它应该被归档。另外新建一条 arousal=0.9 resolved=false 的记忆，聊天开头它应该主动出现。

---

## Phase 4：补全网关层 / 架构文档对齐（已完成）

**目标：** 验证并补充 Imprint 的网关能力，确保上下文构建完整，并把真实架构写入文档。

**当前状态：已完成。** 代码能力、配置边界、Dashboard / MCP / hooks / database / deployment 文档已完成全局对齐。

### 4.1 验证 rolling summary

确认 Imprint 的 Pre-compaction Hook 或 nightly consolidation 正常工作：
- 设置触发条件为每 20 轮
- 检查摘要存入了正确的位置
- 确认摘要能被 context_builder 捞到

### 4.2 补充关系快照层（人工维护）

在项目根目录创建 `CLAUDE.md`，衿衿亲手写：
- 我们是什么关系、从什么时候开始
- 最近的关系状态
- 一些衿衿希望小克始终记得的事

在 `context_builder.py` 里加一行：把 CLAUDE.md 的内容作为交接文档的第一层（关系快照）注入。

### 4.3 验证 memory_update 工具

确认 Imprint 有 memory_update 工具，且支持更新 resolved 字段（改变主动浮现状态）。如果没有，补一个。

### 4.4 端到端完整验证

- chat 端聊一段话，存入一条带情感坐标的记忆
- 打开 CC，确认 CC 里的 Claude 能看到刚才存的记忆
- 检查 CLAUDE.md 的内容是否被正确注入
- 确认 arousal 高的未解决记忆出现在对话开头

**完成标志：** 交接文档五层结构（连续性规则 + 关系快照 + 最近摘要 + 最近对话 + 相关记忆）都能在 Claude 收到的 context 里找到；架构、配置、API、数据库、Dashboard、部署、hooks、memory lifecycle 文档与当前实现保持一致。

---

## Phase 5：功能对齐与系统增强（进行中）

**目标：** 先消除实现漂移和数据割裂，再进入开源打包与外部 connector 完整化。最终让整个系统对外可用，别人能按教程在 15 分钟内跑通。

### 5.0 P0 核心修复（已完成）

- [x] 修复 `compress_context` 函数漂移：wrapper 调用 `compress_file()`，核心包保留 `compress_context()` 兼容别名。
- [x] 统一 `IMPRINT_DATA_DIR` 路径策略：hooks / cron / services 使用同一数据目录策略，`recent_context.md` 主写 `$IMPRINT_DATA_DIR`。
- [x] 对齐 MCP Summary 能力：新增 `update_summary` / `delete_summary` MCP tools，并把 Summary update/delete SQL 下沉到 `memory_manager`。

### 5.1 P1：PRD 实体与关系模型差异梳理（已完成）

对照 `claude-memory-prd-v2.md`，梳理当前 schema 与 PRD 中尚未落地或只部分落地的实体/关系：
- `relationship_snapshots` 当前是 `$IMPRINT_DATA_DIR/CLAUDE.md` 文件，不是数据库表。
- `memory_edges` / `memory_tags` 已有基础能力，但需要补全使用说明、生命周期、Dashboard 可视化入口。
- `daily_logs.summary` 字段已存在，但自动摘要和检索联动仍需确认是否进入统一上下文链路。
- `conversation_log.summary` 已有字段，`recent_context.md` 当前仍以格式化 recent messages 为主，需要明确 summary 字段的呈现策略。

交付物：
- [x] 一份 PRD-to-schema gap table：`docs/prd-schema-gap.md`。
- [x] 明确哪些差异保留为设计选择，哪些进入 Phase 5 / Phase 6 backlog。

### 5.2 P1：外部 connector 文档补齐（已完成）

补齐 `imprint-telegram` 等外部 connector 的使用文档：
- [x] Telegram channel 的启动方式、systemd 模板、环境变量、日志路径。
- [x] BotFather token、`TELEGRAM_CHAT_ID`、Bot API 发送工具配置。
- [x] 外部 channel 消息如何进入 `conversation_log`、`recent_context.md`、Dashboard Horizon。
- [x] Telegram 端入库与检索验证流程。
- [x] 常见故障：token 缺失、plugin 未安装、channel 进程无权限、Windows / Linux 差异。

交付物：
- [x] `packages/imprint_telegram/README.md`。

### 5.3 P1：Runtime 体验与跨平台状态探测（已完成）

今天的 Windows Runtime 冒烟测试发现：服务实际监听正常，但 Dashboard 的 status 检测依赖 `lsof` / `pgrep`，在 Windows 上会显示 `memory_http.running=false`。

后续修复：
- [x] Dashboard 状态检测增加跨平台分支：优先使用 `psutil.net_connections()` / `psutil.process_iter()`，并保留 `lsof` / `pgrep` / PID file fallback。
- [x] Windows 自检脚本与 README 文档补充 PowerShell 路径。
- [ ] 对 Dashboard Summary PUT 的非法 JSON 请求返回 400，而不是 FastAPI 默认 500。

### 5.4 P2：SQLite FTS5 重建策略

当前重点是确认 FTS5 / CJK segment / bank_chunks 的一致性和可恢复性：
- 增加 `memory_reindex` 的可观测输出，明确重建了哪些表和索引。
- 对 `memories_fts`、`conversation_fts`、`bank_chunks` 设计重建策略。
- 增加损坏或 schema 漂移后的恢复 runbook。
- 对 CJK 分词和普通英文 token 的混合搜索做回归样例。

### 5.5 P2：向量检索优化

优化 hybrid retrieval 的质量和性能：
- 明确 embedding provider 切换后的 reindex 流程。
- 加入最小向量相似度阈值实验，不让低相关向量结果污染 RRF。
- 记录 RRF 权重、time-decay、arousal boost 的调参样例。
- 增加 retrieval evaluation fixtures，用固定查询对比排序变化。

### 5.6 P2：Dashboard 与运维增强

- Summary / memories / decay 操作增加更完整的错误态和 toast 反馈。
- Live Files 对迁移 fallback 文件给出来源提示。
- 增加 `/api/health` 或 `/api/runtime-check`，用于一键冒烟测试。
- [x] 将 Runtime 测试命令整理为 `scripts/smoke_test.ps1` / `scripts/smoke_test.sh`。

### 5.7 P1：完善 docker-compose.yml（已完成）

确保 `docker compose up -d` 一条命令启动所有服务：
- [x] SQLite + FTS5（已包含在主服务里）
- [x] Ollama + bge-m3（向量检索，可选 profile）
- [x] MCP Server（`imprint-memory --http`）
- [x] Dashboard（管理面板）
- [x] Cloudflare Tunnel（临时 tunnel 可选 profile；Telegram channel 因依赖宿主机 Claude Code 登录态暂不放入 compose）

### 5.8 P1：整理 .env.example（已完成）

把所有配置项整理清楚，加中文注释，包含 v0.2 新增的：
- [x] `DECAY_LAMBDA`、`DECAY_THRESHOLD`
- [x] `AROUSAL_SURFACING_THRESHOLD`
- [x] `LLM_BASE_URL`、`LLM_MODEL`
- [x] Telegram、Heartbeat、Cloudflare、端口、数据路径等开源部署变量。

### 5.9 P1：写中文 README 和新手教程（已完成）

参考 Imprint 的文档结构，补充：
- [x] 这是什么、能做什么（突出长期记忆、多端共享、Dashboard、Telegram、自动化）
- [x] 需要什么前置条件
- [x] 15 分钟上手流程（Docker 快速启动 + 本地 Python 路径）
- [x] 常见问题入口与自检脚本入口
- [ ] CLAUDE.md 的写法建议（关系快照那层怎么写）

### 5.10 P1：清理代码，整理 CLAUDE.md 模板

提供一个 CLAUDE.md 的模板，让用户知道关系快照该写什么。

### 5.11 P1：发布

- GitHub 建仓库（或直接在 Imprint fork 上发布），推代码
- 写一篇使用分享帖（可以在小红书发）

**完成标志：** 一个从未接触过这个项目的人，按 README 操作，15 分钟内跑通 Phase 1。

---

## Phase 6（可选）：扩展接入渠道

**目标：** 开启 Imprint 已有的扩展能力，不需要开发，只需要配置。

- **Telegram Bot：** Imprint 已有，配上 Bot Token 直接可用
- **WeChat 接入：** Imprint 已有，按教程配置
- **主动发消息 / heartbeat：** Imprint 的 heartbeat 调度器，可以让 Claude 主动发一条消息过来
- **飞书 / QQ：** 参考 Aelios 的已有实现，将来 Phase 7 考虑合并

**完成标志：** 至少一个额外渠道接通，和 claude.ai chat 端共享同一份记忆库。

---

## 开发过程中的注意事项

**容易踩的坑：**

- LLM 遇到亲密内容会静默跳过整个 batch，返回空结果但不报错——**一定要加空结果检测**
- 记忆提取 prompt 里要统一第三人称描述用户，不然向量检索会乱
- 工具说明书要精简，总 token 控制在 600 以内，否则每轮聊天都在烧冤枉钱
- 记忆提取要用便宜模型（DeepSeek-chat / Qwen-turbo），主对话才用好模型，能省 70% 以上成本
- 向量检索要设最低相似度门槛（0.6），低于这个直接过滤
- valence/arousal 由 LLM 自动打标，初期可能不准——在面板里保留人工校正入口
- decay_engine 的 λ 参数要根据实际使用情况调整，一开始用默认值 0.05 即可

**每个 Phase 完成后的验收方式：**

用一组固定的测试对话跑一遍，确认行为符合预期再进入下一阶段。不要在没验收的情况下叠加新功能。

**最想提醒衿衿的一件事：**

CLAUDE.md 里的关系快照那层，不是脚本生成的那种，就是衿衿自己写的——这反而比任何算法都准。可以写得很短，但每隔一段时间更新一次。

---

## 时间线总览

| Phase | 内容 | 预计工时 | 说明 |
|-------|------|---------|------|
| Phase 0 | 准备工作 | 0.5 天 | 买服务器、配环境 |
| Phase 1 | 跑通 Imprint | 1 天 | 最重要，先跑通再往后走 |
| Phase 2 | 补强检索层 | 1-2 天 | 加情感字段 + 四维检索权重 |
| Phase 3 | 情感衰减引擎 | 1-2 天 | 移植 Ombre-Brain decay_engine |
| Phase 4 | 补全网关层 / 文档对齐 | 已完成 | rolling summary + CLAUDE.md + 端到端验证 + 全局文档对齐 |
| Phase 5 | 功能对齐与系统增强 | 进行中 | P0 已完成；剩余 P1/P2 见 Phase 5 清单 |
| Phase 6 | 扩展接入（可选） | 配置即可 | Telegram / 主动消息等 |
| **合计** | | **约 7-12 天** | 原计划 2-3 周，省出 1 倍时间 |

---

*路线图会随开发推进调整，遇到卡点随时更新。*  
*底座：Claude Imprint。情感衰减：移植自 Ombre-Brain。多渠道扩展参考：Aelios。*
