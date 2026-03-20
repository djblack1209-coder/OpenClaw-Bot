# 交易盈利索引 (TRD)

> 分类: 03 - 交易盈利
> 前缀: TRD
> 涵盖: 交易记录、PnL、风控策略、策略迭代

## 自动记忆机制

交易记忆桥接 (`TradingMemoryBridge`) 已于 2026-03-18 启用。
以下事件会自动写入 `SharedMemory` (category=trading):
- 开仓记录 (trade_open_{id}_{symbol})
- 平仓记录 (trade_close_{id}_{symbol})
- 亏损教训 (trade_lesson_{id}, 亏损>$20 时触发)
- 复盘总结 (review_{type}_{date})

## 文件列表

| 编号 | 文件 | 说明 | 条目数 |
|------|------|------|--------|
| (自动记录中，查询 SharedMemory category=trading) | | | |

## 关联资源
- 盈利作战室: `skills/profit-war-room/`
- Alpha研究: `skills/alpha-research-pipeline/`
- 风险闸门: `skills/execution-risk-gate/`
- 回撤开关: `skills/drawdown-kill-switch/`
- PnL日报: `skills/pnl-daily-brief/`

## 决策规则
- 日/周盈利目标未达 → 立即进入恢复模式
- 恢复模式: 诊断→重训→压缩风险→验证→恢复

## 下一可用编号: TRD-001
