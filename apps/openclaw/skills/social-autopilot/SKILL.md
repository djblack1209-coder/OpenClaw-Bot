---
name: social-autopilot
description: |
  AI 自主运营 X/小红书全自动模式。无需 Boss 手动触发，按日程表自动完成：
  热点扫描→选题→内容生成→预检→发布→互动→蹭评→数据复盘。
  触发词：自动运营、autopilot、自主运营、全自动社媒。
metadata:
  category: social-media
  author: openclaw
  version: 1.0.0
---

# Social Autopilot — AI 自主社媒运营

## 定位

这不是等 Boss 下命令的被动模式，而是**完全自主的 AI 运营员**。
每天按照预设日程表自动完成全部运营动作，只在需要决策时通知 Boss。

## 每日自动运营日程

### ☀️ 早间 09:00 — 热点扫描与选题

1. 执行 `node tools/social-hotspot-monitor.mjs --platform all --min-score 6`
2. 扫描结果 + 选题库(`tools/social-topic-library.md`) → 选出今天发布的 2-3 个选题
3. 用 `node tools/social-topic-scorer.mjs` 评分，≥7 分的进入内容生产
4. 结果写入 `memory/social/SOC-001-publish-runs.md`
5. 向 Boss 发送一条简报：「今日选题：[标题1] [标题2]，预计晚8点发」

### 🌙 午间 12:00-13:00 — 互动与蹭评

1. 检查已发布内容的评论区，用 `tools/social-comment-engine.mjs reply` 自动回复
2. 用 `tools/social-comment-engine.mjs scout` 扫描 3-5 个目标帖
3. 用 `tools/social-comment-engine.mjs generate-scout-comment` 生成蹭评内容
4. 通过 Playwright 发布蹭评（需确保浏览器预热）

### 🌆 晚间 19:00 — 内容生产

1. 读取人设 `tools/social-persona.md`
2. 基于早间选题，按人设风格生成完整内容
3. 小红书内容：标题+正文+标签+封面描述
4. X 内容：280字以内观点+引用/对比
5. 执行预检 `node tools/social-publish-preflight.mjs`：
   - AI 身份暴露检测 → 不通过则重写
   - 客服腔/营销号腔检测
   - 标题吸引力评估
6. 通过预检的内容保存为草稿

### 🌃 晚间 20:00-21:00 — 自动发布

1. 确认浏览器登录状态（X + 小红书）
2. 执行 `node tools/social-workflow.mjs publish`
3. 通过 Playwright 完成实际发布
4. 记录发布状态到 `memory/social/SOC-001-publish-runs.md`
5. 发布成功后向 Boss 推送通知（含链接）

### 🌙 晚间 21:00-22:00 — 发布后互动

1. 新帖发布后 1 小时内，密集监控评论区
2. 自动回复所有评论（保持人设风格）
3. 主动蹭 2-3 个相关热帖的评论区

### 🌑 睡前 22:00 — 数据复盘

1. 统计今日发布数据：阅读量、点赞、评论、新增粉丝
2. 对比 KPI 目标（小红书单条阅读>500/X单条>200）
3. 写入 `memory/social/SOC-003-interactions.md`
4. 如有未达标内容，分析原因并调整明日选题方向

## 自动化实现方式

### 方式一：OpenClaw Cron（推荐）

在 OpenClaw 中创建以下 cron 任务：

| 任务名 | 时间 | 动作 |
|--------|------|------|
| 社媒早扫 | 每天 09:00 | 热点扫描 + 选题 + 简报 |
| 社媒午动 | 每天 12:30 | 评论互动 + 蹭评 |
| 社媒晚产 | 每天 19:00 | 内容生产 + 预检 |
| 社媒晚发 | 每天 20:30 | 自动发布（双平台） |
| 社媒复盘 | 每天 22:00 | 数据统计 + 复盘 |

### 方式二：HEARTBEAT.md 集成

在 HEARTBEAT.md 中添加社媒运营检查项，让每次心跳自动检查运营进度。

## 关键文件

| 文件 | 用途 |
|------|------|
| `tools/social-persona.md` | 人设基准 |
| `tools/social-topic-library.md` | 选题库 |
| `tools/social-interaction-strategy.md` | 互动策略 |
| `tools/social-workflow.mjs` | 工作流编排入口 |
| `tools/social-hotspot-monitor.mjs` | 热点扫描 |
| `tools/social-comment-engine.mjs` | 评论引擎 |
| `tools/social-publish-preflight.mjs` | 发布预检 |
| `tools/social-browser-adapter.mjs` | 浏览器发布适配 |
| `scripts/social_browser_worker.py` | Playwright 执行器 |

## 安全边界

- **绝不暴露 AI 身份**：所有内容必须通过人设一致性预检
- **发布失败不重试超过 2 次**：避免重复发布
- **敏感话题不碰**：政治、色情、虚假信息
- **大额变动通知 Boss**：账号异常、封号风险、数据骤降
