---
name: guide
description: 项目使用说明。输出当前 OpenClaw Bot 系统全景概览，帮助 Boss 快速了解项目能力、架构和运营状态。
metadata: {"openclaw":{"emoji":"📖"}}
---

# 使用说明 / Project Guide

当 Boss 输入 `/guide` 或"使用说明"时，输出以下完整项目概览。

## 行为

1. 读取本文件中的项目概览模板
2. 读取 `memory/INDEX.md` 获取当前记忆状态
3. 读取 `.openclaw/openclaw.json` 中 `skills.entries` 获取已启用 skill 数量
4. 读取 `memory/social/SOC-001-publish-runs.md` 获取最新发布统计
5. 汇总后以下方模板输出

## 输出模板

```
📖 OpenClaw Bot 使用说明

━━━━━━ 🏗️ 项目架构 ━━━━━━

OpenClaw Bot 是一套 AI Agent 驱动的全栈自动化系统：

• 🧠 OpenClaw — AI 中枢大脑（Telegram Bot @carven_OpenClaw_Bot）
• 🤖 ClawBot — Python 多 Bot 执行引擎（交易/社媒/闲鱼/浏览器）
• 🖥️ Manager — macOS 原生桌面管理面板
• ⚡ Gateway — 本地网关（端口 18789）

━━━━━━ 📋 可用命令一览 ━━━━━━

【基础】
/guide — 📖 你正在看的这个
/start — 启动待命  /help — 命令列表
/status — 系统状态  /model — 模型切换
/clear — 清上下文  /reset — 重置会话
/usage — 用量统计  /cost — 成本配额

【社媒运营】
/hot — 🔥 抓热点并一键双发 X + 小红书
/post_social — 双平台发布
/post_x — 发 X  /post_xhs — 发小红书
/social_plan — 生成发文计划
/social_persona — 查看当前社媒人设

【交易 & 盈利】
/profit — 💰 盈利作战室
/alpha — 🔬 Alpha 研究流水线
/risk — ⚠️ 交易风险闸门
/brief — 📊 PnL 日报
/recover — 🔄 目标未达恢复重训

【系统管理】
/heal — 🩺 ClawBot 自愈恢复
/channel — 📡 多渠道总控中心
/lane — 🏷️ 群聊分流标签
/dev — 🛠️ 开发任务模式
/coding_agent — 委托编码任务
/github — GitHub 操作

【产研】
"产研团队"/"阿七" — 全流程产研（想法→Spec→Demo→走查）

━━━━━━ 💰 盈利渠道 ━━━━━━

1. 闲鱼 AI 客服 — OpenClaw 部署服务 ¥99 + API Token ¥19.9
2. Upwork 自动接单 — 变现 watcher 自动推送
3. 社媒流量变现 — X(@CodeTiredAI) + 小红书(代码写累了) 引流

━━━━━━ 🤖 自动化能力 ━━━━━━

• 社交发布: 热点监控→选题评分→内容生成→预检→Playwright 自动发布→互动
• 闲鱼客服: WebSocket 实时监控→意图分类→议价/技术专家→自动回复→订单通知
• 交易系统: 回测→风控→自动交易→绩效分析→止损回撤自动停机
• 浏览器自动化: Chrome CDP 预热→X/小红书/Upwork 自动操作

━━━━━━ 📊 当前状态 ━━━━━━

（由 Agent 实时读取填充：已启用 skill 数、发布统计、盈利状态等）

提示: 发送任何问题我都会尽力回答。私聊走主脑模型，群聊走免费模型。
```

## 注意

- 根据实际读取到的数据动态填充"当前状态"部分
- 保持简洁，不超过一屏 Telegram 消息
- 中文输出
