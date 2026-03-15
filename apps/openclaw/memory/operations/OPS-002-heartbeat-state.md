# OPS-002 心跳状态

> 来源: heartbeat-state.json (引用)
> 注意: 实时状态仍存于 heartbeat-state.json，此处仅做索引引用

## OPS-002.1 心跳状态文件
- **路径**: `memory/heartbeat-state.json`
- **用途**: 跟踪邮件/日历/天气等周期检查的最后执行时间
- **格式**: JSON `{ lastChecks: { email: timestamp, ... } }`
