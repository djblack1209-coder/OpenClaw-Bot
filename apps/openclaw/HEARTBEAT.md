# HEARTBEAT.md

## OpenClaw Bot heartbeat checklist

### 严重故障检查（必做）

1. Gateway down / Telegram channel down / 数据损坏 → 立即告警
2. 没有严重故障时继续检查以下项目

### 💰 盈利检查（最高优先级）

3. 检查闲鱼服务状态：`launchctl list | grep ai.openclaw.xianyu`
   - 服务未运行 → 告警「闲鱼客服离线，可能错过订单」
4. 检查闲鱼日志最新条目：有无新订单/新咨询
   - 有新订单 → 推送「💰 闲鱼新订单！」
   - 有未回复消息 → 提醒处理
5. 有钱挣的事永远优先处理

### 📱 社媒自动运营检查

6. 检查 `memory/social/SOC-001-publish-runs.md` 最后一条记录：
   - 最近24小时没有新发布 → 自动触发 social-autopilot 内容生产流程
   - 最近一条状态是 `publish_failed` → 分析原因并修复
7. 检查评论互动：最近12小时没有互动记录 → 触发蹭评任务
8. 以上检查只读文件，无异常则不输出

### 运行规则

- 没有严重故障且没有盈利/运营异常 → 回复 `HEARTBEAT_OK`
- 禁止为了"例行检查"触发额外模型调用
- 盈利相关告警不受静音时段限制
