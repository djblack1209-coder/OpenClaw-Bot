# 功能规格总集

> 合并自原 050-059 + 062 + 065 共 16 个功能规格文档

---

## 一、Telegram 论坛话题切换

# Telegram Forum Topic Cutover

适用场景：你要把当前 supergroup 从 lane 标签分流升级为 Telegram 原生 topic/thread 分流。

## 目标

- 保留现有 7-bot 架构和风控规则。
- 在同一个群里，用 forum topic 做职责隔离（RISK/ALPHA/EXEC/FAST/CN/BRAIN/CREATIVE）。
- 提供一键改写 `/.openclaw/openclaw.json` 的工具和回滚路径。

## 0) 预检（当前群是否已开启 forum）

在项目根目录执行：

```bash
token=$(jq -r '.channels.telegram.accounts.default.botToken // .channels.telegram.botToken' ".openclaw/openclaw.json")
curl -s "https://api.telegram.org/bot${token}/getChat?chat_id=-1003754981982"
```

判定：返回里出现 `"is_forum": true` 代表已开启 forum topic。

## 1) 免费升级步骤（Telegram 客户端）

1. 打开目标群 -> `Edit`/`管理群组`。
2. 打开 `Topics`/`话题` 开关（升级到 forum 形态）。
3. 确认 Bot 管理员权限包含：`can_manage_topics`、`can_send_messages`。

## 2) 创建 7 个 topic（建议命名）

- `RISK-风控`
- `ALPHA-研究`
- `EXEC-执行`
- `FAST-快问`
- `CN-中文`
- `BRAIN-终极推理`
- `CREATIVE-创意`

## 3) 发现 topic 的 message_thread_id

执行：

```bash
node OpenClaw/tools/telegram-topic-discovery.mjs --chat-id -1003754981982 --limit 200
```

你会拿到 `topics[]`，里面包含 `threadId` 与 `topicName`。

## 4) 一键改写 OpenClaw topic 路由

把上一步拿到的 threadId 填进去执行：

```bash
node OpenClaw/tools/apply-telegram-topic-routing.mjs \
  --chat-id -1003754981982 \
  --owner-id 7043182738 \
  --risk 101 \
  --alpha 102 \
  --exec 103 \
  --fast 104 \
  --cn 105 \
  --brain 106 \
  --creative 107
```

脚本会：

- 自动备份当前配置为 `/.openclaw/openclaw.json.bak-topic-*`
- 写入 `channels.telegram.groups.<chatId>.topics.<threadId>`
- 每个 topic 自动设置：`enabled=true`、`requireMention=false`、`groupPolicy=allowlist`

## 5) 验证与切换策略

```bash
openclaw config validate
openclaw cron run 5e401547-128d-4614-bd72-a8e620e8b731
openclaw cron runs --id 5e401547-128d-4614-bd72-a8e620e8b731 --limit 5
```

建议切换顺序：

1. 先保留 lane 标签分流（现网兜底）。
2. 新消息优先在 topic 内测试一段时间。
3. 稳定后再逐步降低 lane 标签依赖。

## 6) 回滚

```bash
latest=$(ls -t ".openclaw"/openclaw.json.bak-topic-* | head -n 1)
cp "$latest" ".openclaw/openclaw.json"
openclaw config validate
```

回滚后立即恢复 lane 标签模式即可。

---

## 二、每日战报


## Objective

Deliver a single daily briefing that aligns market priorities, execution tasks, and system health.

## Inputs

- Overnight market and macro changes
- Existing watchlist and pending actions
- Service health and channel status

## Workflow

1. Summarize overnight developments.
2. Highlight top opportunities and top risks.
3. Show required tasks for the day (execute, monitor, fix).
4. Include what the agent can do proactively without waiting.

## Success metrics

- Faster decision start each morning
- Fewer missed high-priority actions

## Abort conditions

- Missing core inputs (market feed or service health unavailable)

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/custom-morning-brief.md`
- `awesome-openclaw-usecases-src/usecases/inbox-declutter.md`

---

## 三、多渠道指挥中心


## Objective

Operate Telegram, Discord, and other channels as one coordinated control surface.

## Inputs

- Channel configurations
- Alert policy (severity and routing)
- Message templates for status and incidents

## Workflow

1. Use Telegram as primary command lane.
2. Route collaboration updates to secondary channels.
3. Deduplicate notifications across channels.
4. Keep critical incident alerts short and actionable.

## Success metrics

- Reduced channel noise
- Faster incident response
- Consistent delivery confirmation

## Abort conditions

- Credential or channel API failures
- Unknown delivery state on critical alerts

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/multi-channel-assistant.md`
- `awesome-openclaw-usecases-src/usecases/multi-agent-team.md`
- `awesome-openclaw-usecases-src/usecases/multi-channel-customer-service.md`

---

## 四、工作空间 RAG 设计


## 目标

在 OpenClaw 当前工作区上先做一层轻量级 RAG，不追求一开始就上向量数据库，先完成：

1. 工作区内容切块
2. 可追踪 chunk id / 行号
3. 基础召回
4. 降低 ops 日志污染
5. 后续可接 embeddings / rerank

## 第一阶段：静态索引

索引来源：
- `skills/`
- `usecases/`
- `memory/`
- `MEMORY.md`
- `TOOLS.md`
- `USER.md`
- `SOUL.md`
- `AGENTS.md`
- `TELEGRAM_COMMANDS.md`

输出文件：
- `.manager/workspace-index.json`

由脚本生成：
- `tools/workspace-indexer.mjs`

### 当前索引结构（已实现）

每个 chunk 附带：
- `chunkId`：改为 `path#Lx-Ly`
- `source`：`knowledge | memory | journal | ops | reference`
- `fileType`：`markdown | jsonl | json | text`
- `title / sectionTitle`
- `startLine / endLine`
- `mtimeMs`

### 当前切块策略（已实现）

- Markdown：优先按标题 section 切块，再按目标字符数二次切分
- JSONL：按事件组切块，避免整份日志成为单个长块
- 普通文本：按行聚合，避免纯固定长度硬切

## 第二阶段：检索器

当前已补：
- query 归一化
- token 扩展
- 标题 / 路径 / 正文混合打分
- source-aware scoring
- intent-aware boosting
- 默认去重，避免同一文件刷屏
- 结果附带命中理由、line range、source

下一步建议增加：
- embedding 召回
- top-k 合并
- 轻量 rerank
- 只注入最相关 chunks

## 第三阶段：日志污染控制

当前策略：
- 将 `memory/task-runs.jsonl`、`memory/failures.jsonl`、`memory/retrieval-runs.jsonl`、`heartbeat-state.json` 归类为 `ops`
- 默认检索时对 `ops` 降权
- 当 query 明显是排障 / 运行日志意图时，再对 `ops` 回补加权

这样做的目标是：
- 日常知识检索尽量命中 skills / usecases / memory 笔记
- 排障和复盘场景仍能找回运行日志

## 第四阶段：任务接入

优先接入场景：
1. 记忆检索
2. 技能选择
3. usecase 路由
4. 社媒工作流
5. 开发任务上下文准备

## 为什么先这样做

因为现在最缺的是：
- 有组织的 chunk 数据
- 可复用的工作区索引
- 检索前置层
- 知识与运行日志的基本分层

先把这些基础搭好，后续接 embeddings / 向量检索 / rerank 都会顺很多。

---

## 五、社媒内容操作系统


> 从"发布工具"升级为"像人一样运营"的完整系统

## 目标

把 X / 小红书 从"临时发一条"升级为**可持续、可验证、可复盘、有人设、会互动**的内容运营系统。

核心原则：

- **人设先行**：所有内容必须符合统一人设（参考 `tools/social-persona.md`）
- **先过预检，再发布**：不靠手感硬发
- **全程留痕**：每次发布都要留下状态记录，不做黑箱操作
- **失败可定位**：能定位在选题、内容、浏览器执行、账号状态、平台风控中的哪一层
- **双平台改写**：同主题双平台改写，不直接复制
- **像人一样互动**：发内容只是一半，评论区运营和蹭热点同样重要

## 核心文件体系

### 人设与策略层
- `tools/social-persona.md` - 人设指导文件（语气、风格、禁区）
- `tools/social-topic-library.md` - 选题库与内容模板（30+选题方向）
- `tools/social-interaction-strategy.md` - 互动运营策略（评论区+蹭热点）

### 工具层
- `tools/social-workflow.mjs` - 总入口与状态推进
- `tools/social-topic-scorer.mjs` - 选题评分器
- `tools/social-hotspot-monitor.mjs` - 热点监控工具（新增）
- `tools/social-comment-engine.mjs` - 评论互动引擎（新增）
- `tools/social-publish-preflight.mjs` - 发布预检
- `tools/social-publish-plan.mjs` - 发布计划生成
- `tools/social-browser-adapter.mjs` - 浏览器执行适配器
- `tools/social-publish-log.mjs` - 发布日志记录

### 配置层
- `tools/social-browser-targets.json` - 平台目标配置

## 完整运营链路

### 1. 热点监控（每日自动）
```bash
# 生成热点扫描任务
node tools/social-hotspot-monitor.mjs --platform all

# 评估已抓取的热点数据
node tools/social-hotspot-monitor.mjs --platform xhs --raw-data memory/hotspot-raw-xxx.json --min-score 7
```

### 2. 选题评分
```bash
# 对多个选题打分排序
node tools/social-topic-scorer.mjs --platform xhs "选题A" "选题B" "选题C"

# 带详细解释
node tools/social-topic-scorer.mjs --platform xhs --explain "选题A"
```

### 3. 内容生产
- 从 `tools/social-topic-library.md` 选择选题方向
- 按对应的内容骨架模板生成内容
- 确保语气符合 `tools/social-persona.md` 的人设要求
- 标题必须通过"吸引力测试"：自己看到会不会想点？

### 4. 发布预检
```bash
# 预检内容是否符合发布标准
node tools/social-publish-preflight.mjs --platform xhs --title "标题" --text "正文"

# 预检并记录日志
node tools/social-workflow.mjs preflight-log --platform xhs --run-id social-001 --title "标题" --text "正文"
```

### 5. 发布执行
```bash
# 完整发布流程（生成计划 + 执行 + 验证）
node tools/social-workflow.mjs publish --platform xhs --topic "选题" --run-id social-001 --submitted --published --evidence share_link --url "https://..."
```

### 6. 发布后互动（关键！）
```bash
# 生成回复调度计划
node tools/social-comment-engine.mjs schedule --platform xhs --post-id xxx

# 回复评论区
node tools/social-comment-engine.mjs reply --platform xhs --post-id xxx

# 生成单条回复指导
node tools/social-comment-engine.mjs generate-reply --comment "用户评论" --context "帖子主题"
```

### 7. 蹭评论区（每日任务）
```bash
# 获取蹭评论目标列表
node tools/social-comment-engine.mjs scout --platform xhs --category S

# 生成蹭评论指导
node tools/social-comment-engine.mjs generate-scout-comment --post-title "目标帖子标题" --post-summary "摘要"
```

### 8. 数据复盘（每周）
- 查看 `memory/social-publish-runs.jsonl` 分析发布数据
- 查看 `memory/comment-interactions.jsonl` 分析互动数据
- 查看 `memory/hotspot-scan-log.jsonl` 分析热点捕捉效率
- 更新 `tools/social-topic-library.md` 中的选题库

## Publish State Machine（最小可用）

- `idea_selected`
- `draft_ready`
- `preflight_passed`
- `publish_started`
- `publish_submitted`
- `verify_pending`
- `published`
- `publish_failed`
- `needs_manual_review`

### 状态推进规则

- 没有 `draft_ready`，不能进入 `preflight_passed`
- 没有 `preflight_passed`，不能进入 `publish_started`
- `publish_submitted` 后必须进入 `verify_pending`
- `verify_pending` 只能结束于：`published` / `publish_failed` / `needs_manual_review`
- 如果浏览器执行中断，不要默认成功，必须标记 `needs_manual_review` 或 `publish_failed`

## Browser publish adapter（当前实现阶段）

当前工作区已经有：
- `tools/social-workflow.mjs`
- `tools/social-publish-plan.mjs`
- `tools/social-browser-adapter.mjs`
- `tools/social-browser-targets.json`

它们的职责：
- `social-workflow.mjs`：总入口与状态推进
- `social-publish-plan.mjs`：生成平台发布计划（目标页面、所需证据、执行步骤）
- `social-browser-adapter.mjs`：浏览器执行适配器骨架
- `social-browser-targets.json`：平台目标配置（URL、步骤、验证提示）

### 当前阶段能做到
- 生成发布计划
- 生成浏览器任务产物
- 推进发布状态
- 记录成功/失败/人工复核
- 为后续浏览器自动化接入预留统一入口

### 当前阶段还没做到
- 自动控制 X / 小红书真实页面完成最终发布
- 自动抓取真实成功 URL / note id
- 自动截图回写证据

## 失败分类

- `draft_invalid`
- `asset_missing`
- `login_missing`
- `site_blocked`
- `submit_failed`
- `verify_failed`
- `tool_timeout`
- `bad_route`

## 发布前预检清单

### 通用
- 平台是否明确：X / 小红书
- 主题是否明确
- 文案是否最终版
- 是否含敏感风险词
- 是否存在明显错别字 / 占位符 / TODO
- 是否需要图片/链接，如需要则素材已存在

### X
- 主帖是否足够短，能当截图传播
- 是否预留评论区续写
- 是否包含强钩子或结论句

### 小红书
- 标题是否像“结论句”或“问题句”
- 前三行是否可单独成立
- 图文是否优先于纯文本
- 标签是否控制在少量高相关范围

## 发布后验证清单

### 成功证据优先级
1. 分享链接 / 帖子 URL
2. 页面出现明确成功提示
3. 个人主页能看到新帖卡片
4. 草稿箱/发布记录出现对应内容

### 验证要求
- 至少拿到 1 个强证据，才可记为 `published`
- 只有点击过发布按钮但没有证据，不算成功
- 若页面模糊、跳转异常、网络卡住，记为 `needs_manual_review`

## 浏览器操作规则

- 如果为了提取视频内容临时打开浏览器窗口/标签，提取完成后必须关闭。
- 如果是发布任务打开的平台页面，可在发布完成后保留主页面，不保留无关提取窗口。
- 本地 Chrome 已登录会话优先；Browser Relay 作为兜底，而不是默认路径。
- 发布结束后，要么拿到成功证据，要么明确记失败，不允许“应该发出去了”这种模糊结论。

## 推荐最小落地工具

- 选题评分：`node tools/social-topic-scorer.mjs --platform x "topic a" "topic b"`
- 发布预检：`node tools/social-publish-preflight.mjs --platform x --text "..."`
- 发布状态日志：`node tools/social-publish-log.mjs state '{"platform":"x","state":"published"}'`
- 发布计划：`node tools/social-publish-plan.mjs --platform x --run-id social-001 --topic "选题" --text "文案"`
- 浏览器适配器生成计划：`node tools/social-browser-adapter.mjs plan --platform x --run-id social-001 --topic "选题" --text "文案"`
- 浏览器适配器准备任务：`node tools/social-browser-adapter.mjs prepare-run`
- 浏览器适配器写验证结果：`node tools/social-browser-adapter.mjs verify --run-id social-001 --platform x --manual-review`
- 故障日志：`node tools/task-log.mjs failure '{"taskType":"social_post",...}'`

## 成功标准

- 有稳定日更节奏
- 有固定内容模板
- 有数据复盘闭环
- 能筛出可复用爆款结构
- 每条发布都可追溯到“预检 -> 提交 -> 验证 -> 结果”

## 推荐工具清单（更新）

### 发布链路工具（v1.0）
- 选题评分：`node tools/social-topic-scorer.mjs --platform x "topic a" "topic b"`
- 发布预检：`node tools/social-publish-preflight.mjs --platform x --text "..."`
- 发布计划：`node tools/social-publish-plan.mjs --platform x --run-id social-001 --topic "选题" --text "文案"`

### 运营链路工具（v2.0 新增）
- 热点监控：`node tools/social-hotspot-monitor.mjs --platform all`
- 评论回复指导：`node tools/social-comment-engine.mjs generate-reply --comment "用户评论"`
- 蹭评论目标：`node tools/social-comment-engine.mjs scout --platform xhs --category S`
- 回复调度：`node tools/social-comment-engine.mjs schedule --platform xhs --post-id xxx`

## 每日运营SOP

### 早间（9:00-10:00）
1. 运行热点监控，扫描过夜热点
2. 评估热点，决定今日是否追热点
3. 确定今日发布选题

### 午间（12:00-13:00）
1. 检查评论区，回复新评论
2. 去3-5个目标帖子评论区互动

### 晚间（20:00-21:00）
1. 发布当日主力内容
2. 启动回复调度
3. 黄金1小时内回复所有评论

### 睡前（22:00-23:00）
1. 最后一轮评论区检查
2. 记录当日数据
3. 预排明日选题

## 升级指标（v2.0）

- 人设一致性：所有内容读起来像同一个人写的
- 互动率：每条帖子评论区有真实互动
- 评论区活跃度：每天主动在3-5个帖子评论区互动
- 热点响应速度：S级热点2小时内出内容
- 粉丝增长：小红书周增50+，X周增20+

---

## 六、社媒发布日志规范


## 目标

给社媒发布流程补一层最小可用的运行记录，让每次发文都能回答：

- 发的是什么
- 发到哪个平台
- 走到了哪个状态
- 是否真的发成功
- 失败卡在哪一层

## 建议日志文件

- `memory/social-publish-runs.jsonl`

## 推荐字段

```json
{
  "ts": "2026-03-09T18:30:00+08:00",
  "runId": "x-20260309-01",
  "platform": "x",
  "topic": "为什么 AI 自动化内容号正在从拼产量转向拼验证",
  "state": "published",
  "status": "ok",
  "evidence": "post_visible|toast_success|share_link",
  "url": "https://x.com/...",
  "errorType": null,
  "detail": null,
  "nextAction": null,
  "operator": "openclaw"
}
```

## 状态枚举

- `idea_selected`
- `draft_ready`
- `preflight_passed`
- `publish_started`
- `publish_submitted`
- `verify_pending`
- `published`
- `publish_failed`
- `needs_manual_review`

## 记录原则

- 允许同一个 `runId` 写多条记录，表示状态推进
- `published` 必须有 `evidence`，最好同时带 `url`
- `publish_failed` 必须带 `errorType` 和 `nextAction`
- `needs_manual_review` 用于“点了发布但拿不到证据”的灰区

## CLI

- 记录状态：`node tools/social-publish-log.mjs state '{"runId":"x-20260309-01","platform":"x","state":"publish_started"}'`
- 记录成功：`node tools/social-publish-log.mjs state '{"runId":"x-20260309-01","platform":"x","state":"published","evidence":"share_link","url":"https://x.com/..."}'`
- 记录失败：`node tools/social-publish-log.mjs state '{"runId":"x-20260309-01","platform":"x","state":"publish_failed","errorType":"verify_failed","detail":"点击发布后页面卡住","nextAction":"打开个人主页确认是否可见"}'`

## 先落地原则

- 先把状态记下来，再考虑自动汇总
- 先服务排错和复盘，不急着做大而全 dashboard
- 先覆盖 X / 小红书，后续再扩更多平台

---

## 七、自愈控制面


## Objective

Keep OpenClaw gateway and ClawBot services online with fast, targeted auto-recovery.

## Inputs

- LaunchAgent status
- Endpoint health checks
- Service logs and restart history

## Workflow

1. Poll key endpoints and service status.
2. Restart only impacted service first.
3. Re-validate endpoint and dependency chain.
4. Escalate to broader restart only if targeted recovery fails.
5. Record incident and suspected root cause.

## Success metrics

- Mean time to recovery (MTTR)
- Uptime percentage of core endpoints

## Abort conditions

- Repeated restart loops without stabilization
- Upstream dependency unavailable (for example broker endpoint down)

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/self-healing-home-server.md`
- `awesome-openclaw-usecases-src/usecases/aionui-cowork-desktop.md`

---

## 八、Alpha 研究工厂


## Objective

Continuously convert noisy market information into ranked, tradable opportunities.

## Inputs

- Earnings and macro calendars
- Sector news and narrative shifts
- Social sentiment anomalies

## Workflow

1. Scan multi-source feeds.
2. Build ranked watchlist by catalyst quality and timing.
3. Attach entry trigger and invalidation for each setup.
4. Publish shortlist to 严总 with recommended priority.

## Success metrics

- Signal-to-noise ratio of shortlisted setups
- Win rate and expectancy of watchlist-derived executions

## Abort conditions

- Data quality degradation
- Excessive false positives from one source

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/earnings-tracker.md`
- `awesome-openclaw-usecases-src/usecases/multi-source-tech-news-digest.md`

---

## 九、恢复重训模式


## Objective

When profit targets are missed, switch into a strict recovery cycle until performance quality returns.

## Inputs

- PnL history and trade log
- Strategy parameter history
- Current drawdown and volatility context

## Workflow

1. Trigger recovery mode on target miss or drawdown breach.
2. Run postmortem by failure bucket: thesis, timing, sizing, execution.
3. Adjust strategy rules and tighten risk budgets.
4. Validate via dry run/paper run.
5. Resume normal mode only after recovery criteria are met.

## Success metrics

- Drawdown stabilization
- Recovery of positive expectancy
- Reduced rule-violation count

## Abort conditions

- Continued degradation after retraining
- Inability to explain source of losses with evidence

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/polymarket-autopilot.md`
- `awesome-openclaw-usecases-src/usecases/project-state-management.md`

---

## 十、AI 升级路线图


## 背景

结合你提到的视频思路，OpenClaw 目前不应只停留在“会调用模型、会跑技能”的层面，而应往更高一级升级：

- 从单轮助手 → 可复用的企业级 AI 系统
- 从 prompt 驱动 → 检索增强 + 工作流编排
- 从功能能跑 → 稳定、可观测、可评估、可扩展
- 从“知道很多” → “对当前任务上下文检索精准、结果可复盘”

这份文档聚焦：如何把 OpenClaw 往 **RAG / 向量检索 / 企业级生成系统 / 工程化落地** 的方向推进。

---

## 一、可以直接借鉴的视频思路

### 1. 检索增强，而不是只靠上下文硬塞
OpenClaw 现在已经有：
- MEMORY.md
- memory/*.md
- skills/*
- usecases/*
- 本地文档与工作区文件

但这些内容更多还是“静态文件 + 命中式读取”。

应升级为：
- 结构化知识源
- 可搜索、可召回、可重排
- 按任务动态注入上下文

也就是从“文件记忆”升级到：
- **轻量 RAG 层**
- **工作区语义检索层**
- **技能/用例动态召回层**

### 2. 企业级生成系统，不是单点回答
真正强的 AI 系统不是“回答一次很聪明”，而是：
- 输入规范化
- 意图分类
- 检索增强
- 工具路由
- 执行
- 结果校验
- 失败回退
- 结果归档

OpenClaw 已经有一些雏形（skills、cron、browser、subagents），但还缺少明确的“系统编排层设计”。

### 3. 工程化和可观测性
要真正把 OpenClaw 做成长期可用系统，需要补：
- 每次任务的检索来源
- 工具调用轨迹
- 失败原因分类
- 可复盘的输出质量
- 成本 / 延迟 / 命中率统计

---

## 二、全面升级的 5 个主方向

## 方向 A：工作区 RAG 化

### 目标
让 OpenClaw 不只是读文件，而是能“按语义检索工作区知识”。

### 可落地点
1. 为以下内容建立统一检索索引：
   - skills/
   - usecases/
   - MEMORY.md
   - memory/*.md
   - TOOLS.md
   - 未来的 docs/ 或 notes/

2. 检索流程升级为：
   - query 改写
   - top-k 召回
   - 重排（rerank）
   - 只注入最相关片段

3. 检索结果需要带：
   - 文件路径
   - 标题
   - 行号 / chunk id
   - 命中理由

### 价值
- 降低上下文浪费
- 提高回答稳定性
- 提高“记忆命中率”
- 减少重复读文件

---

## 方向 B：技能与用例的“动态路由层”

### 目标
把 skills 和 usecases 从“手动命中”升级成“系统化调度”。

### 现状问题
当前更多依赖：
- 描述触发
- 人工判断
- 单技能 upfront 加载

### 应升级为
1. 意图识别器
   - 问答
   - 开发
   - 运维
   - 投研
   - 社媒运营
   - 自动化发布

2. 任务规划器
   - 是否需要 memory
   - 是否需要 browser
   - 是否需要 exec
   - 是否需要 subagent
   - 是否需要 cron

3. 技能召回器
   - 先选最相关 skill
   - 必要时补充参考 usecase
   - 避免无关技能占上下文

### 价值
- 降低路由失误
- 提升任务命中效率
- 更像“系统编排”，而不是“聊天式硬做”

---

## 方向 C：企业级生成工作流

### 目标
把高价值任务沉淀成固定工作流，而不是每次现场 improvisation。

### 适合优先标准化的工作流
1. **/heal 自愈链路**
   - 服务探活
   - 异常分类
   - 恢复动作
   - 回执结果

2. **/brief 日报链路**
   - 数据收集
   - 风险摘要
   - 行动项输出
   - 历史归档

3. **社媒发布链路**
   - 热点抓取
   - 选题评分
   - 文案生成
   - 配图策略
   - 浏览器发布
   - 数据复盘

4. **开发任务链路**
   - 需求理解
   - 规划
   - subagent 执行
   - 产出检查
   - 变更总结

### 每个工作流都应具备
- 输入 schema
- 输出 schema
- 失败 fallback
- 重试策略
- 审批边界
- 成本控制

---

## 方向 D：可观测性与评估

### 目标
让 OpenClaw 不止“能做”，还要“知道自己做得好不好”。

### 建议补的观测项
1. 每次任务记录：
   - 任务类型
   - 用到哪些 tools
   - 是否用到 memory / browser / exec / cron / subagent
   - 执行耗时
   - 是否失败
   - 失败类型

2. 检索评估：
   - query
   - 命中文档
   - 用户是否认可
   - 是否出现“答非所问”

3. 成本评估：
   - 哪类任务最费 token
   - 哪类任务最常失败
   - 哪类任务适合下放本地模型

4. 输出质量评估：
   - 是否完成任务
   - 是否需要返工
   - 是否命中用户预期

### 可先落地的最小版本
在 `memory/` 下新增：
- `task-runs.jsonl`
- `retrieval-runs.jsonl`
- `failures.jsonl`

---

## 方向 E：社媒与外部运营自动化

### 目标
把 X / 小红书运营从“临时发文”升级成“内容系统”。

### 系统应包括
1. 热点抓取层
   - X 热门话题
   - 中文社区热榜
   - 指定账号跟踪

2. 内容改写层
   - X 短帖
   - 小红书图文
   - 评论续写
   - 标题 A/B 版本

3. 图片策略层
   - 封面模板
   - 信息卡模板
   - 抽象趣味风模板

4. 发布执行层
   - 浏览器 relay
   - 自动填充
   - 发布确认

5. 数据复盘层
   - 曝光
   - 点赞
   - 评论
   - 收藏 / 转发
   - 选题复用

---

## 三、建议的优先级（按收益排序）

## P0：立刻该做
1. 建立 OpenClaw 升级路线图（本文件）
2. 给现有 usecases 加统一“输入/输出/回滚”规范
3. 给关键技能补“何时用 / 何时不用 / fallback”
4. 为社媒命令补完整执行链设计

## P1：高优先级
1. 轻量工作区语义检索索引（已做首版：结构化 chunk metadata + source 分层 + 基础 intent-aware ranking）
2. 技能与 usecase 动态路由层
3. 任务运行日志与失败日志
4. 高频任务工作流模板化

## P2：中期建设
1. 检索 rerank
2. 输出质量评估
3. 内容运营数据闭环
4. 子代理结果验收层

## P3：进一步进化
1. 多知识库分层检索
2. 长期任务规划与自动调度
3. 企业级权限边界和策略引擎
4. 可视化控制面板

---

## 四、我建议马上开始的实际动作

### 第一步：知识层升级
新增一个 `usecases/openclaw-ai-upgrade-roadmap.md`（即本文件）作为总蓝图。

### 第二步：把社媒运营链路产品化
补一套明确 usecase：
- 选题抓取
- 内容生产
- 双平台改写
- 自动发布
- 数据复盘

### 第三步：给 OpenClaw 补任务运行日志
先不搞大系统，先把“每次任务做了什么、成没成”落盘。

### 第四步：设计轻量 RAG
优先服务于：
- memory
- skills
- usecases
- docs

---

## 五、结论

**可以，而且非常值得。**

视频里提到的“向量检索、企业级生成系统、工程化落地”，和 OpenClaw 当前的真实短板是高度对齐的。

如果按这条线继续升级，OpenClaw 会从：
- 会调用模型的本地助手

升级为：
- **具备检索增强、工作流编排、可观测性和长期运营能力的本地 AI 控制平面**

这才是长期能打的方向。

---

## 十一、盈利作战室


## Objective

Run a high-intensity profit engine that prioritizes expected value while preserving survivability.

## Inputs

- Current capital and exposure
- Daily/weekly profit targets
- Max drawdown constraints
- Event and catalyst feed

## Workflow

1. Generate candidate trades from event-driven catalysts.
2. Filter for asymmetry and liquidity.
3. Pass every candidate through `execution-risk-gate`.
4. Execute only high-conviction setups.
5. Review outcomes and feed misses into `recovery-retrain-mode`.

## Success metrics

- Positive expectancy
- Profit target hit rate
- Controlled drawdown profile

## Abort conditions

- Risk limits breached
- Regime shift invalidates current strategy assumptions

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/polymarket-autopilot.md`
- `awesome-openclaw-usecases-src/usecases/earnings-tracker.md`

---

## 十二、任务运行日志规范


## 目标

给 OpenClaw 增加最小可用、可校验、可长期追加的任务运行记录，便于复盘、调优和排错。

## 记录文件

- `memory/task-runs.jsonl`
- `memory/failures.jsonl`
- `memory/retrieval-runs.jsonl`

每行一条 JSON；允许保留 `{"_comment":"..."}` 这种初始化注释行。

---

## CLI 用法

### 追加日志

```bash
node tools/task-log.mjs <task|failure|retrieval> '<json-payload>'
```

### 校验现有日志文件

```bash
node tools/task-log.mjs validate <task|failure|retrieval> [file]
```

说明：
- 脚本会自动补 `ts`
- 会清理控制字符和多余空白，降低 JSONL 被脏文本污染的概率
- 会做最小 schema 校验；缺关键字段会拒绝写入
- 未识别字段不会自动保留，避免日志结构长期漂移

---

## 通用字段

三类日志都支持以下通用字段（按需写）：

```json
{
  "ts": "2026-03-09T10:25:56.200Z",
  "taskId": "task-20260309-001",
  "sessionId": "agent:main:subagent:...",
  "taskType": "dev|research|heal|brief|browser_extract",
  "status": "ok|error|partial|running|queued|skipped|cancelled",
  "notes": "补充说明"
}
```

字段说明：
- `ts`: ISO 时间戳；不传则自动生成
- `taskId`: 任务级唯一标识，建议同一任务链复用
- `sessionId`: 代理/会话 ID，便于串联上下文
- `taskType`: 任务分类；task/failure 必填，retrieval 可选
- `status`: 状态字段；不同日志类型可用值略有不同
- `notes`: 简短补充说明

---

## task-runs.jsonl

### 必填字段

- `taskType`

### 推荐字段

```json
{
  "ts": "2026-03-09T10:25:56.200Z",
  "taskId": "task-20260309-001",
  "sessionId": "agent:main:main",
  "taskType": "social_post",
  "inputSummary": "把研究摘要改写成 X 帖子",
  "tools": ["browser", "exec"],
  "usedSkill": "summarize",
  "usedUsecase": "social-content-operating-system",
  "status": "ok",
  "durationMs": 12345,
  "itemCount": 1,
  "outputs": ["x_post_draft"],
  "warnings": ["used cached cookies"],
  "tags": ["social", "x"],
  "notes": "已生成并待人工确认"
}
```

### task 专属字段

- `inputSummary`: 输入摘要
- `tools`: 实际调用工具列表
- `usedSkill`: 使用的 skill 名
- `usedUsecase`: 使用的 usecase 名
- `durationMs`: 总耗时
- `itemCount`: 产出条目数
- `outputs`: 关键输出标记
- `warnings`: 非致命风险/异常
- `tags`: 轻量标签

---

## failures.jsonl

### 必填字段

- `taskType`
- `detail`

### 推荐字段

```json
{
  "ts": "2026-03-09T10:25:56.200Z",
  "taskId": "task-20260309-001",
  "sessionId": "agent:main:main",
  "taskType": "browser_extract",
  "status": "error",
  "errorType": "login_missing|site_blocked|tool_timeout|bad_route",
  "failedTool": "browser",
  "tools": ["browser", "exec"],
  "detail": "页面被登录墙拦截，未拿到正文",
  "nextAction": "切到本机 Chrome profile 后重试",
  "retryable": true,
  "durationMs": 4200,
  "warnings": ["relay tab detached"]
}
```

### failure 专属字段

- `errorType`: 失败类型
- `failedTool`: 最终失败发生在哪个工具
- `detail`: 失败原因摘要
- `nextAction`: 建议下一步
- `retryable`: 是否适合重试
- `durationMs`: 失败前耗时
- `tools`: 涉及工具列表
- `warnings`: 上下文风险提示

状态允许值：`error | partial | cancelled | skipped`

---

## retrieval-runs.jsonl

### 必填字段

- `query`

### 推荐字段

```json
{
  "ts": "2026-03-09T10:31:14.103Z",
  "taskId": "task-20260309-rag-01",
  "sessionId": "agent:main:main",
  "taskType": "research",
  "status": "ok",
  "query": "RAG social content logging",
  "rewrittenQuery": "task run logging spec retrieval logging",
  "sources": ["usecases/task-run-logging-spec.md", "MEMORY.md"],
  "topHits": ["usecases/task-run-logging-spec.md#1", "MEMORY.md#3"],
  "hitCount": 2,
  "quality": "good",
  "retrievalMs": 180,
  "indexVersion": "workspace-index@2026-03-09",
  "notes": "命中 spec 与 roadmap"
}
```

### retrieval 专属字段

- `query`: 原始查询
- `rewrittenQuery`: 改写后的查询
- `sources`: 命中的源文件路径列表
- `topHits`: 命中的 chunk / path#line 列表
- `hitCount`: 命中数
- `quality`: `good | weak | miss`
- `retrievalMs`: 检索耗时
- `indexVersion`: 索引版本/快照标识

状态允许值：`ok | partial | error`

---

## 落地原则

- 继续保持 JSONL append-only，简单直接
- 写入前做轻量规范化，避免脏数据把整份日志搞坏
- 只保留稳定字段，避免“想记什么就塞什么”导致 schema 漂移
- 先服务复盘，再追求自动分析
- 高频任务优先接入：`/heal`、`/brief`、社媒发布、视频提取、开发任务、workspace 检索

## 建议实践

1. 同一任务链尽量复用 `taskId`
2. 子代理/会话运行尽量补 `sessionId`
3. 失败同时记 `task` + `failure` 时，`task.status` 和 `failure.status` 保持一致语义
4. 检索日志尽量记录 `hitCount` 和 `quality`
5. 定期跑：

```bash
node tools/task-log.mjs validate task
node tools/task-log.mjs validate failure
node tools/task-log.mjs validate retrieval
```
