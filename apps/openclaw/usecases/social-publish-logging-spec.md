# Social Publish Logging Spec

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
