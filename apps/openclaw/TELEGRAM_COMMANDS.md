# Telegram Command Shortcuts (严总)

These commands are bound to workspace skills for faster triggering in Telegram.

## Shortcut map

- `/risk` -> `execution-risk-gate`
- `/brief` -> `pnl-daily-brief`
- `/lane` -> `telegram-lane-router`
- `/cost` -> `cost-quota-dashboard`
- `/dev` -> `dev-todo-mode`

## Usage examples

- `/risk check current plan`
- `/lane [RISK] 今天仓位是否需要降杠杆？`
- `/cost`
- `/dev 修复总控中心里 provider 空白并回归测试`

## 严总 direct-equivalent shortcuts

These are the shortcuts 严总 should prefer in Telegram when they want roughly the same effect as a direct assistant request:

- Development / config execution -> `/dev <task or path>`
- Cost / quota check -> `/cost`
- Risk / execution gate -> `/risk <task>`

## Lane 标签（非 forum 群分流）

- `[RISK]` / `#风控` -> Claude Sonnet
- `[ALPHA]` / `#研究` -> Qwen 235B
- `[EXEC]` / `#执行` -> DeepSeek V3
- `[FAST]` / `#快问` -> GPT-OSS
- `[CN]` / `#中文` -> DeepSeek V3
- `[BRAIN]` / `#终极` -> Claude Opus
- `[CREATIVE]` / `#创意` -> Claude Haiku

## Forum topic 原生分流（升级方案）

- 运行手册：`OpenClaw/usecases/telegram-forum-topic-cutover.md`
- Topic ID 探测：`node OpenClaw/tools/telegram-topic-discovery.mjs --chat-id -1003754981982 --limit 200`
- 一键改写 topic 路由：`node OpenClaw/tools/apply-telegram-topic-routing.mjs ...`

## Local AI system upgrade helpers

- 工作区索引：`node tools/workspace-indexer.mjs`
- 工作区检索：`node tools/workspace-search.mjs "<query>"`
- 工作区检索并记录：`node tools/workspace-search.mjs --log --task-id task-001 --session-id agent:main:main "<query>"`
- 工作区检索（允许同文件多块）：`node tools/workspace-search.mjs --all --top 12 "<query>"`
- 任务日志：`node tools/task-log.mjs task '{"taskType":"..."}'`
- 检索日志：`node tools/task-log.mjs retrieval '{"query":"..."}'`
- 故障日志：`node tools/task-log.mjs failure '{"taskType":"..."}'`

## Social publishing helpers

- 社媒总入口评分：`node tools/social-workflow.mjs score --platform x "topic a" "topic b"`
- 社媒总入口规划：`node tools/social-workflow.mjs plan --platform x "topic a" "topic b"`
- 社媒总入口预检：`node tools/social-workflow.mjs preflight --platform x --text "你的主帖文案"`
- 社媒预检并自动记状态：`node tools/social-workflow.mjs preflight-log --platform x --run-id social-001 --topic "选题" --text "你的主帖文案"`
- 社媒草稿就绪记状态：`node tools/social-workflow.mjs draft-log --platform x --topic "选题" --run-id social-001`
- 社媒发布状态推进：`node tools/social-workflow.mjs publish --platform x --topic "选题" --run-id social-001 --submitted --manual-review`
- 社媒直接记状态：`node tools/social-workflow.mjs log state '{"runId":"x-20260309-01","platform":"x","state":"publish_started"}'`
- 社媒选题评分：`node tools/social-topic-scorer.mjs --platform x "topic a" "topic b"`
- 社媒选题评分（含解释）：`node tools/social-topic-scorer.mjs --platform xhs --explain "topic a" "topic b"`
- 社媒预检：`node tools/social-publish-preflight.mjs --platform x --text "你的主帖文案"`
- 小红书预检：`node tools/social-publish-preflight.mjs --platform xhs --title "标题" --text "正文" --tags "AI,效率" --images 3`
- 发布状态日志：`node tools/social-publish-log.mjs state '{"runId":"x-20260309-01","platform":"x","topic":"...","state":"preflight_passed"}'`
- 发布失败日志：`node tools/social-publish-log.mjs state '{"runId":"x-20260309-01","platform":"x","state":"publish_failed","errorType":"submit_failed","detail":"页面点击后报错","nextAction":"改走 Browser Relay 复试"}'`

## Social publishing recommended flow

1. 先跑选题评分，决定优先级
2. 完成双平台改写，不直接复制
3. 发布前跑 preflight
4. preflight 通过后记 `preflight_passed`
5. 执行浏览器发布并推进 `publish_started -> publish_submitted -> verify_pending`
6. 至少拿到一个成功证据后，再记 `published`
7. 如果没有成功证据，不要口头算成功，记 `needs_manual_review` 或 `publish_failed`

## Notes

- Native skill command registration is forced for Telegram via `channels.telegram.commands.nativeSkills=true`.
- If native menu registration is delayed, typed slash commands still work.
- `@carven_OpenClaw_Bot` 现在作为中枢大脑：私聊和显式 @ 提问走主脑模型；后台扫描/简单活优先留给免费链路。
