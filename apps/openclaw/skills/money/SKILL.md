---
name: money
description: |
  盈利总控台。查看所有收入渠道状态、今日/本周收入、待处理订单。
  触发词：/money、挣钱、盈利、收入、变现。
metadata:
  category: monetization
  author: openclaw
  version: 1.0.0
---

# Money — 盈利总控台

当 严总 输入 `/money` 或"挣钱"时，执行以下检查并汇报。

## 行为

### 1. 检查所有收入渠道状态

读取并汇报以下渠道的健康状态：

#### 渠道 A：闲鱼 AI 客服（最快变现）

- **商品**：OpenClaw 远程部署服务 ¥99 + 免费 API Token ¥19.9
- **检查项**：
  - 闲鱼 LaunchAgent 是否运行：`launchctl list | grep ai.openclaw.xianyu`
  - Cookie 是否有效（检查 packages/clawbot 的闲鱼日志）
  - 今日订单数和收入
  - 待回复消息数

#### 渠道 B：社媒引流变现

- **路径**：X/小红书内容 → 个人品牌 → 付费咨询/部署服务
- **检查项**：
  - 今日发布数、互动数据
  - 粉丝增长
  - 是否有 DM 咨询

#### 渠道 C：Upwork 接单

- **检查项**：
  - 变现 watcher 是否活跃
  - 待投标 job 数
  - 进行中项目状态

### 2. 输出格式

```
💰 盈利总控台

━━━ 收入概览 ━━━
今日收入: ¥___
本周收入: ¥___
本月收入: ¥___

━━━ 渠道状态 ━━━

🛒 闲鱼 AI 客服
  状态: 🟢运行中 / 🔴已停止
  今日订单: _单  收入: ¥_
  待回复: _条
  Cookie: 有效/需更新

📱 社媒引流
  X 粉丝: _  今日+_
  小红书粉丝: _  今日+_
  今日发布: _条  互动: _次

💼 Upwork
  状态: 🟢/🔴
  进行中: _单  待投标: _个

━━━ 行动建议 ━━━
1. [最高优先级的盈利行动]
2. [次优先级]
```

### 3. 主动行动

如果发现渠道状态异常，主动修复：
- 闲鱼 Cookie 过期 → 提醒 严总 更新 Cookie
- 闲鱼服务未运行 → 自动启动 `launchctl load`
- 社媒今日未发 → 触发 social-autopilot
- Upwork 有新 job 匹配 → 推送给 严总

## 盈利启动清单（第一块钱计划）

### 最快路径：闲鱼（预计 1-3 天出单）

1. **确保服务运行**：
   ```bash
   launchctl load ~/Library/LaunchAgents/ai.openclaw.xianyu.plist
   ```

2. **确保商品上架**：
   - OpenClaw 远程部署服务 ¥99（标题：「AI Agent 一键部署 | 远程手把手 | 全平台可用」）
   - 免费 API Token ¥19.9（标题：「GPT/Claude 免费 API 接口 | 无限额度 | 即买即用」）

3. **确保 Cookie 有效**：定期检查闲鱼 WebSocket 连接状态

4. **优化商品描述**：加入更多关键词（AI部署、ChatGPT、Claude、免费API、低价接口）

### 中期路径：社媒变现（预计 2-4 周起量）

1. 先把 X + 小红书日更做起来（social-autopilot）
2. 粉丝破 500 后开始接软广/产品体验
3. 在个人简介放闲鱼链接引流

### 长期路径：Upwork 技术接单

1. 注册/完善 Upwork Profile
2. 开启自动 job 匹配推送
3. 以 AI Agent 部署为卖点接单

## 每日盈利检查（可作为 HEARTBEAT 任务）

每次心跳检查时，花 5 秒看一下：
1. 闲鱼有没有新消息未回复
2. 今天有没有出单
3. 社媒有没有商业意向的 DM

有钱挣的事优先级永远最高。
