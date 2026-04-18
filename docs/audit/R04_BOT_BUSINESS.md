# R04 Telegram Bot 业务场景审计

> **轮次**: R4 | **状态**: 待执行 | **预估条目**: ~40
> **审计角色**: CPO + Staff Engineer
> **前置条件**: R3 完成
> **验证基线**: `cd packages/clawbot && pytest tests/ --tb=no -q 2>&1 | tail -5`

---

## 4.1 投资业务链路（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R4.01 | UX | `src/invest/` | 用户说"分析特斯拉"→ 意图识别 → 调用分析 → 返回报告 全链路 | 跟踪代码路径 | ⬜ |
| R4.02 | UX | `src/invest/` | AI 投票机制：多模型共识 → 投资建议 → 用户确认 → 执行 | 验证完整链路 | ⬜ |
| R4.03 | 设计 | `src/invest/` | 信号追踪：record_prediction → validate → vote_history | 验证三管道 | ⬜ |
| R4.04 | 设计 | `src/invest/` | yfinance 数据获取：60s 缓存 + 新鲜度检测 | 检查缓存逻辑 | ⬜ |
| R4.05 | 设计 | `src/invest/` | 回测系统(QuantStats)：HTML 报告生成 | 验证报告输出 | ⬜ |
| R4.06 | 设计 | `src/freqtrade_bridge.py` | Freqtrade 桥接：策略加载/信号转发/状态同步 | 检查连接逻辑 | ⬜ |
| R4.07 | UX | `src/invest/` | 持仓展示：格式化/盈亏颜色/币种 | 检查消息模板 | ⬜ |
| R4.08 | UX | `src/invest/` | 日报/周报自动推送：内容完整性 | 检查定时任务 | ⬜ |

## 4.2 社媒业务链路（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R4.09 | UX | `src/social/` | 用户说"发一条微博"→ compose → review → publish 全链路 | 跟踪代码路径 | ⬜ |
| R4.10 | 设计 | `src/social/` | browser-use 浏览器采集：是否正确初始化和复用 | 检查浏览器生命周期 | ⬜ |
| R4.11 | 设计 | `src/social/` | 数据分析管道：采集 → post_engagement → 报告 → 学习 | 验证完整链路 | ⬜ |
| R4.12 | 设计 | `src/social/` | PostTimeOptimizer：最佳发布时间学习 | 检查算法和数据源 | ⬜ |
| R4.13 | UX | `src/social/` | 多平台发文（微博/Twitter/小红书等）统一接口 | 检查适配器模式 | ⬜ |
| R4.14 | 设计 | `src/social/` | Autopilot 自动驾驶模式：CRUD + 定时发文 | 检查调度和内容生成 | ⬜ |
| R4.15 | 设计 | `src/social/` | 图片生成（AI生图）集成 | 检查 fal.ai/Volcengine 调用 | ⬜ |
| R4.16 | UX | `src/social/` | 草稿箱 CRUD：保存/编辑/删除/恢复 | 检查持久化 | ⬜ |

## 4.3 闲鱼客服链路（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R4.17 | UX | `src/xianyu/` | QR 登录 → Cookie 获取 → WebSocket 监听 → 自动回复 全链路 | 跟踪代码路径 | ⬜ |
| R4.18 | 安全 | `src/xianyu/` | 底价注入防护：是否无法通过 prompt injection 获取底价 | 检查过滤规则 | ⬜ |
| R4.19 | 设计 | `src/xianyu/` | 10msg/min 限速：是否正确实现 | 检查限速器 | ⬜ |
| R4.20 | 设计 | `src/xianyu/` | 自动接受价格上限机制 | 检查价格比较逻辑 | ⬜ |
| R4.21 | 设计 | `src/xianyu/` | WS 心跳修复 + 重连熔断器 | 检查重连逻辑 | ⬜ |
| R4.22 | UX | `src/xianyu/` | 利润核算 + 转化标记 + 商品排行 | 检查数据聚合 | ⬜ |
| R4.23 | UX | `src/xianyu/` | 库存低预警 + 通知异步化 | 检查告警触发 | ⬜ |
| R4.24 | 设计 | `src/xianyu/xianyu_admin.py` | 闲鱼管理面板（10端点）是否全部可用 | 逐一验证 | ⬜ |

## 4.4 生活自动化链路（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R4.25 | UX | `src/execution/` | 提醒系统：创建/周期性/同义词触发/北京时区 | 验证完整流程 | ⬜ |
| R4.26 | UX | `src/execution/` | 记账系统：收入/支出/月预算/超支告警/17个分类 | 验证分类识别 | ⬜ |
| R4.27 | UX | `src/execution/` | 话费水电费余额追踪 + 低余额告警 | 检查定时检查逻辑 | ⬜ |
| R4.28 | UX | `src/execution/` | 购物比价：四级降级 + 降价提醒监控 | 验证降级链 | ⬜ |
| R4.29 | 设计 | `src/execution/` | price_watches 降价监控 6h 定时检查 | 检查调度器 | ⬜ |
| R4.30 | UX | `src/execution/` | ticker 防误触发（股票代码 vs 日常词汇） | 检查过滤规则 | ⬜ |
| R4.31 | 设计 | `src/execution/wechat_coupon.py` | 微信每日优惠券自动领取 | 检查 mitmproxy 集成 | ⬜ |
| R4.32 | 设计 | `src/execution/` | 月度聚合报表自动生成 | 检查数据聚合 | ⬜ |

## 4.5 Kiro Gateway（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R4.33 | 设计 | `kiro-gateway/main.py` | OpenAI 兼容端点 /v1/chat/completions | curl 测试 | ⬜ |
| R4.34 | 设计 | `kiro-gateway/main.py` | Anthropic 兼容端点 /v1/messages | curl 测试 | ⬜ |
| R4.35 | 安全 | `kiro-gateway/main.py` | CORS 配置：是否正确限制 origins | 检查配置 | ⬜ |
| R4.36 | 安全 | `kiro-gateway/main.py` | 请求大小限制(10MB) 是否生效 | 检查中间件 | ⬜ |

## 4.6 通知系统（4 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R4.37 | 设计 | `src/notifications.py` | P0 通知 3 次重试机制 | 检查重试逻辑 | ⬜ |
| R4.38 | 设计 | `src/notifications.py` | Telegram 告警通知渠道 | 检查发送逻辑 | ⬜ |
| R4.39 | 设计 | `src/wechat_bridge.py` | 微信通知推送（一向推送） | 检查 iLink API 调用 | ⬜ |
| R4.40 | 设计 | `src/notifications.py` | 关机刷新批处理 + EventBus 异常日志 | 检查 shutdown hook | ⬜ |

---

## 执行检查清单

- [ ] 基线快照
- [ ] 每条业务链路至少跟踪到用户可见的输出格式
- [ ] 检查所有外部 API 调用的超时和重试
- [ ] 回归测试
- [ ] 更新 CHANGELOG.md
