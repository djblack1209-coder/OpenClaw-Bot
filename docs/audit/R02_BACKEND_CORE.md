# R02 后端核心引擎审计

> **轮次**: R2 | **状态**: 待执行 | **预估条目**: ~50
> **审计角色**: CTO + VP Security + Staff Engineer
> **前置条件**: R1 完成
> **验证基线**: `cd packages/clawbot && pytest tests/ --tb=no -q 2>&1 | tail -5`

---

## 2.1 FastAPI 服务器核心（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R2.01 | Bug | `src/api/rpc.py:108` | **HI-NEW-01**: `_rpc_system_status()` 引用 `os` 未导入，运行时 NameError | 添加 `import os`，运行相关测试 | ⬜ |
| R2.02 | Bug | `src/api/routers/ws.py:95-97` | **HI-NEW-02**: WebSocket 事件 popleft 多客户端会丢消息 | 改为每个客户端独立队列或广播模式 | ⬜ |
| R2.03 | Bug | `src/api/routers/ws.py:84` | **HI-NEW-03**: WebSocket 初始状态获取无异常保护 | 加 try/except，降级发送空状态 | ⬜ |
| R2.04 | 安全 | `src/api/server.py` | API Token 验证逻辑：是否使用常量时间比较（防时序攻击） | 检查 `hmac.compare_digest` 使用 | ⬜ |
| R2.05 | 安全 | `src/api/server.py` | CORS 配置：是否仅允许 localhost，生产环境无通配符 | 读取 CORS 中间件配置 | ⬜ |
| R2.06 | 安全 | `src/api/server.py` | 请求大小限制 middleware 是否正确工作（10MB） | 检查 middleware 实现 | ⬜ |
| R2.07 | 设计 | `src/api/server.py` | 生产环境 docs 是否禁用（/docs /redoc） | 检查 `docs_url=None` 条件 | ⬜ |
| R2.08 | 设计 | `src/api/routers/` | 14 个 router 文件的端点命名是否统一（RESTful 规范） | 逐一检查路由定义 | ⬜ |

## 2.2 API 路由端点逐一审查（10 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R2.09 | 设计 | `src/api/routers/system.py` | system 路由：ping/status/daily-brief/notifications/services | curl 测试每个端点 | ⬜ |
| R2.10 | 设计 | `src/api/routers/trading.py` | trading 路由：positions/pnl/signals/dashboard/vote/kline/portfolio | 检查输入验证和错误处理 | ⬜ |
| R2.11 | 设计 | `src/api/routers/social.py` | social 路由：analytics/topics/compose/publish/research/metrics | 检查异步操作和超时 | ⬜ |
| R2.12 | 设计 | `src/api/routers/memory.py` | memory 路由：search/stats/delete/update | 检查权限控制 | ⬜ |
| R2.13 | 设计 | `src/api/routers/omega.py` | omega 路由：status/cost/events/tools（jina/image/video） | 检查外部 API 调用的错误处理 | ⬜ |
| R2.14 | 设计 | `src/api/routers/controls.py` | controls 路由：trading/social controls/scheduler CRUD | 检查状态一致性 | ⬜ |
| R2.15 | 设计 | `src/api/routers/conversation.py` | conversation 路由：sessions CRUD/send message | 检查 SSE 流的错误处理 | ⬜ |
| R2.16 | 设计 | `src/api/routers/xianyu.py` | xianyu 路由：QR generate/status/conversations | 检查 QR 码生成逻辑 | ⬜ |
| R2.17 | 设计 | `src/api/routers/newapi.py` | newapi 路由：status/channels/tokens CRUD | 检查代理逻辑 | ⬜ |
| R2.18 | 设计 | `src/api/routers/evolution.py` | evolution 路由：scan/proposals/gaps/stats/history | 检查自进化逻辑 | ⬜ |

## 2.3 Brain 决策引擎（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R2.19 | 设计 | `src/bot/brain.py` | Brain 主逻辑：消息→意图识别→任务分发→响应 | 跟踪完整调用链 | ⬜ |
| R2.20 | 设计 | `src/bot/brain.py` | 意图识别三级漏斗：中文NLP→fast_parse→LLM降级 | 验证降级链是否完整 | ⬜ |
| R2.21 | 设计 | `src/bot/brain.py` | 错误处理：LLM 超时/限流/异常的降级策略 | 检查 try/except 覆盖 | ⬜ |
| R2.22 | 设计 | `src/intent/` | 意图识别模块：fast_parse 正则是否覆盖所有注册命令 | 对照 COMMAND_REGISTRY.md | ⬜ |
| R2.23 | 设计 | `src/bot/proactive_engine.py` | 主动智能引擎：定时检查+事件触发+安静时段过滤 | 检查定时器和过滤逻辑 | ⬜ |
| R2.24 | 设计 | `src/event_bus.py` | EventBus 事件总线：事件注册/发布/订阅是否有内存泄漏风险 | 检查监听器清理机制 | ⬜ |

## 2.4 LLM 路由与 API 池（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R2.25 | 配置 | `config/llm_routing.json` | LLM 路由配置：提供商优先级、模型映射、fallback 链 | 对照 API_POOL_REGISTRY.md | ⬜ |
| R2.26 | 安全 | `src/api_pool/` | API Key 管理：轮换逻辑、死 Key 禁用、余额检测 | 检查 Key 状态机 | ⬜ |
| R2.27 | 安全 | `src/api_pool/` | Key 脱敏：日志中是否只显示前8字符 | grep 日志输出 | ⬜ |
| R2.28 | 设计 | `src/api_pool/` | 负载均衡模式（BALANCED）是否正确实现 | 检查轮询/权重逻辑 | ⬜ |
| R2.29 | 设计 | `src/litellm_client.py` 或等效 | LiteLLM 集成：配置是否外化到 JSON（T5 完成） | 验证无硬编码 | ⬜ |
| R2.30 | 安全 | HI-462 | ~360处 logger 可能泄露 API Key 的模式 | 批量 grep + 修复 | ⬜ |
| R2.31 | 设计 | `src/api_pool/` | iflow Key 7天有效期自动检测+告警 | 检查过期检测逻辑 | ⬜ |
| R2.32 | 设计 | `src/api_pool/` | 熔断器(CircuitBreaker)逻辑：开/半开/关状态转换 | 检查状态机实现 | ⬜ |

## 2.5 数据持久化（6 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R2.33 | 安全 | `src/` 全目录 | SQLite 注入风险：是否使用参数化查询 | grep SQL 拼接模式 | ⬜ |
| R2.34 | 设计 | `src/` 全目录 | 所有 SQLite 数据库是否启用 WAL 模式 | 检查 PRAGMA journal_mode | ⬜ |
| R2.35 | 设计 | `src/` 全目录 | DB 自动清理（每日03:00）是否正确配置 | 检查调度器 | ⬜ |
| R2.36 | 设计 | `src/` 全目录 | DB 自动备份（每日04:00）是否正确配置 | 检查备份脚本 | ⬜ |
| R2.37 | 设计 | `src/memory/` | SmartMemory→SharedMemory→TieredContextManager 管道 | 跟踪数据流 | ⬜ |
| R2.38 | 设计 | `src/memory/` | mem0 集成：是否正确初始化和使用 | 对照 mem0 官方文档 | ⬜ |

## 2.6 安全基线（8 条）

| # | 分类 | 位置 | 审计内容 | 验证方式 | 状态 |
|---|------|------|---------|---------|------|
| R2.39 | 安全 | `src/security.py` | sanitize_input() 实现：是否覆盖 XSS/注入/prompt injection | 检查过滤规则 | ⬜ |
| R2.40 | 安全 | `src/` 全目录 | 所有外部输入是否经过验证（Telegram 消息/API 请求/WebSocket） | grep 输入处理入口 | ⬜ |
| R2.41 | 安全 | `src/` 全目录 | 硬编码密钥/Token 扫描 | `grep -rn "sk-\|api_key\|password\|secret" src/` | ⬜ |
| R2.42 | 安全 | `src/` 全目录 | 日志安全：是否有敏感信息泄露到日志 | 检查 logger 调用 | ⬜ |
| R2.43 | 安全 | `src/api/` | SSRF 防护：是否有对外部 URL 的请求验证 | 检查 httpx/requests 调用 | ⬜ |
| R2.44 | 安全 | `src/` 全目录 | 异常处理：是否有静默异常（bare except / except: pass） | grep 模式 | ⬜ |
| R2.45 | 安全 | `src/` 全目录 | create_task 是否都有异常回调（防幽灵任务） | grep `create_task` | ⬜ |
| R2.46 | 设计 | `src/config_validator.py` | 配置校验：启动时是否检查必要环境变量 | 读取校验逻辑 | ⬜ |

---

## 执行检查清单

- [ ] 基线快照
- [ ] 优先修复 HI-NEW-01/02/03 三个确认级 Bug
- [ ] 安全扫描完成后登记新发现到 HEALTH.md
- [ ] 每次修复后回归测试
- [ ] 更新 CHANGELOG.md
