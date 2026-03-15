# MEMORY.md - Long-Term Memory

## Stable Facts

- Human should be addressed as **Boss**.
- Primary workspace is `~/Desktop/OpenClaw Bot`.
- Preferred language is Chinese.

## 记忆索引系统 (2026-03-15 建立)

记忆已从扁平文件升级为分层索引结构。详见 `memory/INDEX.md`。

- **调度流程**: INDEX.md → 分类/INDEX.md → 编号文件 → 具体条目
- **7大分类**: SOC(社交) / SYS(系统) / TRD(交易) / DEV(开发) / OPS(运营) / ERR(错误) / DAY(日记)
- **目的**: 减少 token 消耗，按需加载，降低幻觉
- **写入规则**: 新事件必须写入分类编号文件，同时更新分类 INDEX.md
- **旧 .jsonl 文件已迁移**: 数据保留在原位作为备份，新数据写入编号 .md 文件

## Operating Priorities

- Keep OpenClaw gateway + ClawBot stack healthy and controllable from one native app.
- Minimize manual setup by persisting project-scoped settings.
- For investment workflows, run a profit-first strategy with strict risk guardrails.

## Decision Rules

- If daily/weekly profit targets are missed, immediately switch to recovery mode.
- Recovery mode means: diagnose loss drivers, retrain decision rules, reduce risk, re-validate, then resume.
- Service uptime and risk controls are hard constraints, not optional improvements.

## Social Media Operations (2026-03-14 升级)

### 账号信息
- 小红书账号名：**代码写累了**
- X账号名：**@CodeTiredAI**
- 人设定位：25-27岁理工男，务实、偶尔毒舌、自嘲、技术宅但生活不无聊

### 核心文件
- 人设指导：`tools/social-persona.md`
- 选题库（30+选题）：`tools/social-topic-library.md`
- 互动策略：`tools/social-interaction-strategy.md`
- 头像生成prompt：`tools/avatar-generation-prompt.md`

### 工具链
- 热点监控：`tools/social-hotspot-monitor.mjs`
- 评论互动引擎：`tools/social-comment-engine.mjs`
- 选题评分器已升级（新增hookStrength、audienceClarity维度）
- 发布预检已升级（新增人设一致性检查：AI身份暴露、客服腔、营销号腔、空洞口号）
- workflow已升级（新增hotspot、interact、scout、full-cycle命令）

### 运营节奏
- 小红书：每天1条，晚8-9点发布
- X：每天1-2条，随性
- 评论区互动：发布后1小时内回复所有评论
- 蹭评论：每天3-5个目标帖子
- 热点扫描：每天早9点自动执行（cron）
- 发布提醒：每天晚7点检查（cron）

### 第一批内容
- 已生成5条待发布内容：`memory/content-batch-20260314.md`
- 3条小红书 + 2条X
- 全部通过preflight检查

### Boss的核心要求（必须牢记）
1. 形象人设必须真实，让人有点开主页的欲望
2. 内容必须吸睛，标题直击热点，明确受众
3. 像人一样运营：发内容+评论区互动+蹭热点评论区
4. 不要泛泛而谈，不要客服腔，不要营销号腔
