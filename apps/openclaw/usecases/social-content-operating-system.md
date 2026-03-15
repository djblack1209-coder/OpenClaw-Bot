# Social Content Operating System v2.0

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
