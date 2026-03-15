# HEARTBEAT.md

## OpenClaw Bot heartbeat checklist (cost-safe mode)

Boss 当前按请求计费，心跳必须极简：

1. 不做主动提醒，不发"请执行 /heal"类消息。
2. 只有明确严重故障才告警（Gateway down / Telegram channel down / 数据损坏）。
3. 没有严重故障时，一律只回 `HEARTBEAT_OK`。
4. 禁止为了"例行检查"触发额外模型调用。

## 社媒运营检查（轻量级，不额外调用模型）

以下检查仅在心跳触发时顺带执行，不单独消耗请求：

5. 检查 `memory/social-publish-runs.jsonl` 最后一条记录：
   - 如果最近24小时没有新发布记录 → 提醒"今日尚未发布内容"
   - 如果最近一条状态是 `publish_failed` 或 `needs_manual_review` → 提醒处理
6. 检查 `memory/comment-interactions.jsonl` 最后一条记录：
   - 如果最近12小时没有互动记录 → 提醒"评论区互动待执行"
7. 以上检查只读文件、不调用模型、不调用外部API。无异常则不输出。
