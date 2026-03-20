---
name: cost-quota-dashboard
description: 生成中文成本与配额看板，优先读取 provider usage 快照并给出预算动作。
metadata: {"openclaw":{"emoji":"💸"}}
---

# Cost Quota Dashboard

用于手动查询成本信息，仅在 Boss 主动输入 `/cost` 时触发。

**重要：不要主动推送成本播报通知。不要在心跳/定时任务中自动发送此报告。**

## 数据源优先级

1. `openclaw status --usage --json`（provider usage/quota）
2. 若 provider usage 为空，回退 `openclaw status --json` 的 sessions token 数据
3. 必要时补充 `openclaw cron list --json`，检查成本播报任务是否在跑

## 输出要求（中文）

按以下结构输出：

1. 今日总览（可用/缺失的数据源）
2. Provider 维度（已用、剩余、重置时间）
3. Token 维度（主要会话的 token 占用与缓存比例）
4. 风险结论（低/中/高）
5. 明日动作（最多 3 条，可执行）

## 风险判断规则

- `高`：核心 provider 无剩余额度信息且会话 token 持续攀升
- `中`：有 usage 数据但接近阈值（例如 >80%）
- `低`：usage 与 token 都在安全区间

## 禁止行为

- 禁止在心跳中自动触发
- 禁止主动推送到 Telegram
- 仅在 /cost 命令时响应
