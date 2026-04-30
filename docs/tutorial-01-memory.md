# 教程一：给 Claude.ai 装上永久记忆

> 这是 Claude Imprint 教程系列的第一篇。
>
> 你不需要会写代码。每一步都可以打开 Claude Code，把你想做的告诉它，让它帮你完成。

---

## 你将得到什么

完成这篇教程后，你的 Claude.ai 对话会有这些新能力：

- **记住你说过的事**——关掉对话，换个窗口，过几天再来，它还记得
- **语义搜索**——不用原话，说"我之前提过我喜欢什么"它也能找到
- **主动记忆**——你可以随时说"记住这个"，它就存下来了
- **记忆是你的**——数据全部存在你自己的电脑上，不在云端

---

## 先理解整体架构

在开始之前，先搞清楚这几个组件是干什么的，它们之间怎么配合。不然操作的时候会很懵。

```
你的电脑                                    互联网
┌────────────────────────────┐
│                            │
│  memory.db (SQLite)        │         ┌──────────────┐
│    ↕                       │         │              │
│  memory_mcp.py (HTTP模式)  │ ←tunnel→│  Claude.ai   │
│    监听 localhost:8000     │         │  (你的对话)   │
│                            │         └──────────────┘
└────────────────────────────┘
         ↑
    Cloudflare Tunnel
    把你本地的 8000 端口
    安全地暴露到一个公网域名
```

四个角色：

1. **memory.db** — 一个 SQLite 数据库文件，存你所有的记忆。就是一个文件，在你电脑上，不依赖任何云服务。
2. **memory_mcp.py** — 记忆服务器。它读写 memory.db，并且把"记住""搜索""忘记"这些操作变成 Claude 能调用的工具（MCP 工具）。
3. **Cloudflare Tunnel** — 一条安全隧道。Claude.ai 在云端，你的电脑在家里，中间需要一条路。Tunnel 的作用就是：让 Claude.ai 能访问到你本地的记忆服务器，不用你有固定 IP，不用开放端口。
4. **Claude.ai 的 Custom Connector** — Claude.ai 自带的功能，让它能连接外部工具。你把 Tunnel 的地址填进去，Claude.ai 就知道去哪里找你的记忆服务器了。

**数据流**：Claude.ai 发出请求 → 经过 Tunnel → 到达你电脑上的 memory_mcp.py → 读写 memory.db → 结果原路返回。

---

## 关于向量搜索

记忆系统支持两种搜索方式：

- **关键词搜索（FTS5）**——直接匹配文字。你存了"我喜欢草莓"，搜"草莓"能搜到。免费，不需要额外安装。
- **向量语义搜索（bge-m3）**——理解意思。你存了"我喜欢草莓"，搜"我爱吃什么水果"也能搜到。需要安装 Ollama 跑一个本地嵌入模型。

实际搜索时两种方式会混合使用（加上时间衰减——越新的记忆权重越高），综合出最相关的结果。

**向量搜索是可选的。** 不装也能用，只是搜索只靠关键词匹配。但如果你希望 Claude 能"理解"你的记忆而不是死板地匹配文字，强烈建议装上。

---

## 你需要准备什么

- **Claude Code**（Pro 或 Max 订阅）—— 用来帮你执行安装步骤
- **Python 3.11+** —— macOS 自带的可能版本太低，CC 会帮你检查
- **一台常开的电脑** —— 记忆服务器跑在你电脑上，电脑关了它就停了
- **Cloudflare 账号**（免费注册）—— 用来创建 Tunnel

可选：
- **一个域名** —— 如果你想要固定的 Tunnel 地址。没有也行，Cloudflare 提供免费临时地址（但每次重启会变）
- **Ollama** —— 如果你想要向量语义搜索

---

## 开始搭建

下面的每一步，你都可以直接把说明贴给 Claude Code，让它帮你做。

### 第一步：下载项目、安装依赖

打开 Claude Code，告诉它：

> "帮我把 claude-imprint 项目 clone 到桌面，创建 Python 虚拟环境，安装依赖。"

它会执行：
```
git clone https://github.com/Qizhan7/claude-imprint.git ~/Desktop/claude-imprint
cd ~/Desktop/claude-imprint
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> **什么是虚拟环境？** 就是一个独立的 Python 空间，装的东西不会影响你电脑上其他 Python 项目。不是必须的，但推荐。

### 第二步：注册 MCP Server（本地）

这一步让 Claude Code 在本地也能用记忆工具。

> "帮我把 memo-clover 注册为 user 级别的 MCP server。"

```
claude mcp add -s user memo-clover -- memo-clover
```

注册之后，所有 Claude Code 窗口都能用 `memory_remember`、`memory_search` 等工具了。

> **什么是 MCP？** Model Context Protocol，Anthropic 的标准协议，让 Claude 能调用外部工具。你不需要理解协议细节，只需要知道：注册了 MCP server = 给 Claude 装了新工具。

### 第三步：（可选）安装向量搜索

> "帮我安装 Ollama 和 bge-m3 嵌入模型。"

```
brew install ollama
ollama pull bge-m3
```

装完后记忆系统会自动检测到 Ollama 并启用向量搜索。不装的话，搜索只用关键词，也能用。

### 第四步：测试本地记忆

这时候你可以先在 Claude Code 里试试：

> "记住：我喜欢吃草莓，不喜欢香菜。"

然后开一个**新的** Claude Code 窗口：

> "我喜欢吃什么？"

如果它答得出来，说明本地记忆已经在工作了。

---

## 连接到 Claude.ai

到这一步，记忆系统在本地已经跑起来了。接下来让 Claude.ai 也能用它。

### 第五步：启动 HTTP 模式

记忆服务器有两种模式：
- **stdio 模式**（默认）—— 给 Claude Code 本地用的
- **HTTP 模式** —— 给外部访问用的（Claude.ai 通过 Tunnel 连进来）

> "帮我用 HTTP 模式启动记忆服务器。"

```
cd ~/Desktop/claude-imprint
python3 memory_mcp.py --http
# 会在 localhost:8000 上运行
```

这个进程需要一直跑着。关掉了 Claude.ai 就连不上了。

### 第六步：生成安全凭证

Claude.ai 连你的服务器需要认证（不然任何人知道地址都能读你的记忆）。

> "帮我生成 OAuth 凭证，保存到 ~/.imprint-oauth.json。"

它会生成三个随机密钥：client_id、client_secret、access_token。后面要用。

### 第七步：创建 Cloudflare Tunnel

这是把你本地的 8000 端口暴露到公网的步骤。

**方式 A：临时隧道（最快，测试用）**

> "帮我用 cloudflared 创建一个临时隧道到 localhost:8000。"

```
cloudflared tunnel --url http://localhost:8000
```

它会给你一个类似 `https://xxx-yyy-zzz.trycloudflare.com` 的地址。**缺点：每次重启地址会变**，你得重新去 Claude.ai 改 Connector 设置。

**方式 B：固定隧道（推荐，一劳永逸）**

需要你有一个域名（在 Cloudflare 管理的），或者愿意买一个（便宜的几块钱一年）。

> "帮我创建一个固定的 Cloudflare Tunnel，绑定到 memory.我的域名.com，指向 localhost:8000。"

CC 会帮你完成 `cloudflared tunnel create`、DNS 配置等步骤。配好之后地址永远不变。

### 第八步：在 Claude.ai 上添加 Connector

这一步需要你手动操作（在浏览器里）：

1. 打开 Claude.ai → **Settings → Connectors → Add Custom Connector**
2. 填入你的 Tunnel 地址（第七步得到的 URL）
3. 展开 **Advanced Settings**，填入 OAuth Client ID 和 Client Secret（第六步生成的，在 `~/.imprint-oauth.json` 里）
4. 点 **Add**

Claude.ai 会自动发现你的记忆服务器提供的所有工具。

### 第九步：教 Claude.ai 怎么用

Connector 连上了，但 Claude.ai 默认不会主动用这些工具。你需要在 Claude.ai 的 **Custom Instructions**（设置 → 自定义指令）里告诉它：

> 你有一个外部记忆系统。遵守以下规则：
> - 当我让你记住什么，用 `memory_remember` 存储
> - 当你不确定我之前说过什么，用 `memory_search` 搜索
> - 不要说"我不记得"——先搜记忆再说
> - 重要的信息主动帮我记住，不用我每次都说"记住这个"

你可以根据自己的需求调整措辞。如果你已经有 Profile / Custom Instructions，把这段加到最后就行。

---

## 验证

打开一个新的 Claude.ai 对话，试试：

1. **存记忆**："记住我是天蝎座，11月4号生日"
2. **关掉这个对话，开一个新的**
3. **搜记忆**："我是什么星座？"

如果它能答出来——恭喜，你的 Claude.ai 有永久记忆了。

---

## 要一直开着的东西

搭好之后，你需要保持以下两个进程一直运行：

1. **memory_mcp.py --http** —— 记忆服务器
2. **cloudflared tunnel run** —— Cloudflare Tunnel

电脑关机或这两个进程停了，Claude.ai 就连不上记忆了（但本地 Claude Code 不受影响，因为它走的是 stdio 模式，不依赖 HTTP 和 Tunnel）。

> **小贴士**：macOS 可以用 `caffeinate -s` 防止电脑休眠。项目自带的 `start-all.sh` 脚本可以一键启动所有服务。

---

## 记忆系统的细节

搭完之后，了解一下这些机制可以帮你更好地使用：

### 记忆分类

每条记忆有一个分类标签：
- **facts** —— 事实（"我住在奥克兰"、"我乳糖不耐"）
- **events** —— 事件（"今天去攀岩了"、"3月14号庆祝了生日"）
- **tasks** —— 待办（"下周交论文"）
- **experience** —— 经验教训（"上次这样做踩坑了"）
- **general** —— 其他

你可以在让 Claude 记忆的时候指定分类，也可以不指定让它自己判断。

### 混合搜索是怎么算的

搜索结果的排名由三个因素加权决定：

| 因素 | 权重 | 作用 |
|---|---|---|
| 向量相似度 | 40% | 语义理解——意思相近的记忆排前面 |
| 关键词匹配 | 40% | 精确匹配——包含搜索词的记忆排前面 |
| 时间衰减 | 20% | 新鲜度——越近的记忆权重越高 |

这意味着：如果你一年前说"我喜欢草莓"，上周说"最近不太想吃草莓了"，搜"我喜欢什么水果"时，最近的那条会排更前面。

### Knowledge Bank

除了数据库里的条目，记忆系统还会索引 `memory/bank/` 目录下的 Markdown 文件。你可以在这些文件里写更长的、结构化的信息：

- `preferences.md` —— 你的偏好、习惯
- `relationships.md` —— 你提到过的人、关系
- `experience.md` —— 技术经验、教训

这些文件也会被向量搜索覆盖到。你可以手动编辑，也可以让 Claude 帮你维护。

### 每日日志

系统会自动生成每日日志文件（`memory/YYYY-MM-DD.md`），记录当天发生的重要事情。这些日志是追加写入的，不会被覆盖。

---

## 常见问题

**Q: 电脑关机了记忆会丢吗？**
不会。记忆存在 memory.db 文件里，开机后重新启动服务就行。

**Q: Claude.ai 说找不到工具 / 连接失败？**
检查三件事：memory_mcp.py --http 在跑吗？cloudflared tunnel 在跑吗？Connector 的地址和凭证填对了吗？

**Q: 不装 Ollama 能用吗？**
能用，搜索会退化成纯关键词匹配。搜"我喜欢什么水果"可能搜不到"我爱吃草莓"，但搜"草莓"能搜到。

**Q: 我有多台电脑怎么办？**
记忆系统跑在一台电脑上就行。其他设备通过 Claude.ai（走 Tunnel）访问同一个记忆库。

**Q: 记忆越来越多会不会变慢？**
SQLite 很能扛。几万条记忆不会有明显变慢。

---

## 下一步

现在你有了一个有记忆的 Claude.ai。下一篇教程，我们让它连上 Telegram 或微信——你可以在手机上随时找它聊天，而且它还记得你们之前说过的一切。

→ [教程二：连接社交软件（Telegram / 微信）](tutorial-02-channels.md)
