---
name: telegram-lane-router
description: 非 forum 群的 Telegram 分流指挥台，用 lane 标签替代 topic/thread。
metadata: {"openclaw":{"emoji":"🧭"}}
---

# Telegram Lane Router

用于当前 Telegram 群 **不是 forum** 时的多智能体分流。

## 目标

- 用显式标签提升指令颗粒度，避免多 bot 抢答。
- 让 严总 可以一眼指定“这条消息该谁处理”。

## Lane 协议

- `[RISK]` / `#风控` -> 风险闸门（Claude Sonnet）
- `[ALPHA]` / `#研究` -> 研究规划（Qwen 235B）
- `[EXEC]` / `#执行` -> 执行与技术（DeepSeek V3）
- `[FAST]` / `#快问` -> 快速答复（GPT-OSS）
- `[CN]` / `#中文` -> 中文表达优化（DeepSeek V3）
- `[BRAIN]` / `#终极` -> 深度推理（Claude Opus）
- `[CREATIVE]` / `#创意` -> 文案创意（Claude Haiku）

## 执行规则

1. 优先识别 `@bot` 提及，其次识别 lane 标签。
2. 若存在 lane 标签，只允许目标 lane 对应 bot 回复。
3. 输出必须包含：`lane`、`负责人`、`下一步动作` 三项。
4. 如果消息无 lane 且无 `@bot`，按默认智能路由处理。

## 回复模板

- `lane`: `<RISK/ALPHA/...>`
- `负责人`: `<bot 名称>`
- `下一步动作`: `<1-3 条可执行动作>`
