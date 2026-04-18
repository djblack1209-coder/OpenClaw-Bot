# CHANGELOG

> 格式规范: 每条变更必须包含 `领域` + `影响模块` + `关联问题`。详见 `docs/sop/UPDATE_PROTOCOL.md`。
> 领域标签: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`

## 按月查看

- [2026-04 月变更记录](CHANGELOG/2026-04.md) — 最新
- [2026-03 月变更记录](CHANGELOG/2026-03.md)

---

## 最近更新（2026-04）

## 2026-04-19 — 技术债清理第2批: 稳定性+功能+数据完整性修复（11项）
> 领域: `backend`, `trading`, `xianyu`, `ai-pool`, `social`
> 影响模块: `litellm_router`, `xianyu_live`, `cmd_ibkr_mixin`, `position_monitor`, `invest_tools`, `nlp_ticker_map`, `drafts`, `broker_bridge`
> 关联问题: HI-522, HI-527, HI-541, HI-567, HI-570, HI-575, HI-576, HI-577, HI-578, HI-580, HI-585

### 稳定性修复 (3项)
1. **HI-522: 风控竞态锁已确认**: check_trade() 共享状态读取已在 `_state_lock` 内完成（上批已修复，本批验证确认）
2. **HI-527: 幽灵任务修复**: litellm_router 启动健康摘要 create_task 添加 `_log_task_exception` done_callback
3. **HI-567: 预算追踪原子化**: broker_bridge 的 `total_spent/budget` read-modify-write 操作用 `asyncio.Lock` 保护

### 闲鱼修复 (3项)
4. **HI-577: app-key 硬编码清理**: 默认值从代码中移除，改为 `XIANYU_APP_KEY` 环境变量读取
5. **HI-578: 通知 FIFO 逐出**: `_notified_chats` 从 set 改为 OrderedDict，超限时 `popitem(last=False)` 逐出最旧条目，不再 clear() 全部清空
6. **HI-580: 自动发货异步化**: 延时发货从 `await asyncio.sleep(120s)` 阻塞主路径改为 `create_task` 后台执行

### 交易修复 (3项)
7. **HI-575: 手动交易记录**: /ibuy /isell 成功后调用 `TradingJournal.open_trade()` 记录交易历史
8. **HI-570: 时间止损修复**: position_monitor naive/aware datetime 混合比较改为统一转换后再比较
9. **HI-576: 行情并行获取**: invest_tools `get_quick_quotes` 从串行循环改为 `asyncio.gather()` 并行查询 + earnings_calendar datetime 统一为 naive

### 功能增强 (2项)
10. **HI-541: ticker 黑名单**: nlp_ticker_map 新增 ~120 个常见英语单词黑名单（AT/IT/TO/BE/GO 等不再误识别为股票代码）
11. **HI-585: 草稿持久化**: drafts.py 从纯内存 dict 改为 `~/.openclaw/drafts.json` 文件持久化（threading.Lock 保护 + uuid4 ID + 向后兼容代理）

### 文件变更
- `src/litellm_router.py` — 新增 `_log_task_exception` + create_task 加 callback
- `src/xianyu/xianyu_live.py` — OrderedDict 通知 + app-key 环境变量 + 自动发货异步化
- `src/bot/cmd_ibkr_mixin.py` — /ibuy /isell 交易记录
- `src/position_monitor.py` — datetime 统一处理
- `src/invest_tools.py` — 并行查询 + datetime 修复
- `src/bot/nlp_ticker_map.py` — ticker 黑名单
- `src/execution/social/drafts.py` — JSON 持久化重写
- `src/broker_bridge.py` — 预算操作加锁

## 2026-04-19 — 技术债清理第1批: 安全+交易+配置修复（15项）
> 领域: `security`, `trading`, `xianyu`, `backend`, `infra`, `deploy`
> 影响模块: `xianyu.py(API)`, `xianyu_agent`, `wechat_coupon`, `wechat_bridge`, `trading_pipeline`, `auto_trader`, `broker_bridge`, `_lifecycle`, `_scheduler_daily`, `launchagents`, `newsyslog`, `docker-compose`
> 关联问题: HI-582~594 (15项修复)

### 安全修复 (8项)
1. **HI-582: 闲鱼 API 认证加固**: 所有 /xianyu/* 端点添加 `Depends(verify_api_token)` 路由级认证
2. **HI-583: Cookie 不再返回前端**: QR 登录确认后 Cookie 保存到服务端 .env，API 响应不含明文 Cookie
3. **HI-584: 闲鱼 prompt injection 防护**: system_prompt 移到最前面 + 用户数据用 XML 标签隔离 + 安全警告加强
4. **HI-586: 微信凭证安全**: 5个模块级全局变量合并为 `_CredentialStore` 类（`__slots__` + `__repr__` 屏蔽 token 值）
5. **HI-587: SSL 验证恢复**: `verify_ssl=False` → `True`，证书问题通过 `SSL_CERT_FILE` 环境变量解决
6. **HI-588: Token 文件安全**: 默认路径从 `/tmp/` → `~/.openclaw/`，写入后 `chmod 0o600`
7. **HI-590: Gateway token 弱默认值移除**: plist 默认值改空 + launcher.sh 从 `~/.openclaw/gateway_token` 读取
8. **HI-591: VPS IP 硬编码清理**: plist 中 IP/端口默认值改空 + `StrictHostKeyChecking=accept-new` → `yes`

### 交易安全修复 (4项)
9. **HI-569: 幽灵持仓修复**: IBKR 降级执行明确标记 `status="simulated"` + 无 portfolio 时返回错误
10. **HI-572: 日交易计数修复**: `confirm_proposal()` 执行成功后递增 `_today_trades`
11. **HI-573: 预算重置修复**: `reset_budget` 从 `IBKR_BUDGET` 环境变量读取，调用方传 `_ibkr.budget` 保留当前额度
12. **HI-574: 持仓恢复时间修复**: `entry_time` 解析失败时记录 WARNING（含 symbol/id/原始值）

### 配置修复 (3项)
13. **HI-592: newsyslog 日志路径**: 全部更新为 `~/Library/Logs/OpenClaw/` 与 plist 一致
14. **HI-593: browser-bootstrap bash -c exec**: 改用统一的 `/bin/bash -c exec` 模式 + 日志路径统一
15. **HI-594: 端口冲突修复**: goofish 从 8000 改为 8001 + 镜像版本锁定

### 文件变更
- `packages/clawbot/src/api/routers/xianyu.py` — API 认证 + Cookie 不返回
- `packages/clawbot/src/xianyu/xianyu_agent.py` — prompt injection 防护
- `packages/clawbot/src/wechat_bridge.py` — _CredentialStore 类替代全局变量
- `packages/clawbot/src/execution/wechat_coupon.py` — SSL + Token路径 + 代理安全
- `packages/clawbot/src/trading_pipeline.py` — 模拟降级标记
- `packages/clawbot/src/auto_trader.py` — 日交易计数
- `packages/clawbot/src/broker_bridge.py` — 预算重置从环境变量读取
- `packages/clawbot/src/trading/_lifecycle.py` — entry_time 解析日志
- `packages/clawbot/src/trading/_scheduler_daily.py` — 保留当前预算
- `tools/launchagents/ai.openclaw.gateway.plist` — token 默认值清空
- `tools/launchagents/gateway-launcher.sh` — 从配置文件读取 token
- `tools/launchagents/ai.openclaw.heartbeat-sender.plist` — IP/端口默认值清空 + SSH 加固
- `tools/launchagents/ai.openclaw.browser-bootstrap.plist` — bash -c exec + 日志路径
- `tools/newsyslog.d/openclaw.conf` — 日志路径全量更新
- `packages/clawbot/docker-compose.goofish.yml` — 端口 8001 + 版本锁定

---

## 2026-04-19 — R10+R11 部署运维+端到端集成验证（55 条目 / 0 修复 / 8 技术债）
> 领域: `infra`, `deploy`, `docs`
> 影响模块: `launchagents`, `docker-compose`, `newsyslog`, `MODULE_REGISTRY`, `DEPENDENCY_MAP`
> 关联问题: R10+R11 HI-590~596

### R10 部署运维审计 (30 条目 / 0 修复 / 5 技术债)
- Docker 配置安全加固: 网络隔离 ✅ / 非 root ✅ / 资源限制 ✅ / cap_drop ✅ / 端口 127.0.0.1 ✅
- VPS 服务器端: 需人工 SSH 验证 (R10.01-R10.08, R10.09-R10.14, R10.15-R10.18)
- 心跳+故障转移: 架构正确，IP 硬编码需移除（HI-591）
- macOS LaunchAgent: Gateway token 硬编码弱值（HI-590）/ browser-bootstrap 未用 bash -c exec（HI-593）
- newsyslog 日志轮转: 路径与 plist 不匹配，实际无效（HI-592）
- 灾难恢复指南: 不存在（HI-595）

### R11 端到端集成验证 (25 条目 / 0 修复 / 3 技术债)
- COMMAND_REGISTRY.md: 99 命令全部有记录 ✅
- MODULE_REGISTRY.md: 254 vs 实际 256+，偏差 ~2 个（HI-596）
- DEPENDENCY_MAP.md: 80+ vs requirements.txt 288 行，偏差较大（HI-596）
- goofish + kiro-gateway 端口冲突 8000（HI-594）

---

## 2026-04-19 — R9 闲鱼+社媒+微信+工具链审计（35 条目 / 4 修复 / 14 技术债）
> 领域: `xianyu`, `backend`, `security`
> 影响模块: `xianyu_live`, `xianyu.py(API)`, `jina_reader`, `drafts`, `wechat_coupon`, `wechat_bridge`
> 关联问题: R9 HI-577~589

### R9 闲鱼+社媒+微信+工具链审计 (35 条目 / 4 修复)
1. **License LIKE 注入修复 (HI-577a)**: `LIKE '%buyer_id%'` 模糊匹配可能错误吊销其他用户 License → 改为精确匹配
2. **API limit 校验 (HI-578a)**: get_xianyu_conversations 的 limit 参数无上限 → 添加 `min(max(1,limit),100)`
3. **floor 变量未初始化 (HI-579a)**: 底价变量在 if 块内赋值、块外引用可能 NameError → 初始化 `floor = None`
4. **Jina URL 编码 (HI-580a)**: 查询参数未 URL 编码直接拼接 → `urllib.parse.quote(query)`

### 审计通过项 (17 项)
- 闲鱼 WebSocket 心跳/重连/熔断器正常运行
- 10msg/min 频率限制 + prompt 注入防护 + sanitize_input 安全消毒
- 社媒 browser-use 浏览器生命周期管理 + 排期准确性
- 微信 iLink API 推送 + TypeScript 插件架构合理
- OMEGA 工具链: Jina/TTS/OCR 超时控制到位

### 技术债 (14 项 — 登记 HEALTH.md)
- app-key 硬编码 / _notified_chats 粗暴清空 / 底价 10 倍上限 / 自动发货阻塞
- License 明文消息 / API 端点无认证 / Cookie 响应明文 / prompt injection 风险
- 草稿内存存储 / 微信凭证全局变量 / SSL 验证禁用 / Token /tmp 全局可读 / 系统代理影响

### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — LIKE 注入修复 + floor 初始化
- `packages/clawbot/src/api/routers/xianyu.py` — limit 参数校验
- `packages/clawbot/src/tools/jina_reader.py` — URL 编码

---

## 2026-04-19 — R8 投资交易系统深度审计（40 条目 / 4 修复 / 10 技术债）
> 领域: `trading`, `backend`
> 影响模块: `broker_bridge`, `trading_pipeline`, `auto_trader`, `ai_team_voter`, `risk_manager`, `position_monitor`
> 关联问题: R8 HI-567~576

### R8 投资交易系统深度审计 (40 条目 / 4 修复)
1. **IBKR connect() 死锁修复 (HI-567a)**: asyncio.Lock 不可重入，Gateway 启动后递归调用 connect() 导致死锁 → 消除递归，在锁内直接重试
2. **DecisionValidator fail-closed (HI-568a)**: 决策验证异常时放行交易(fail-open) → 改为拒绝交易(fail-closed)
3. **AutoTrader 风控绕过修复 (HI-569a)**: 风控计算失败时用 20% 仓位 fallback 绕过 → 改为跳过该候选
4. **AI 投票异常弃权 (HI-570a)**: bot 抛异常时假 HOLD 票计入共识统计 → 设置 abstained=True

### 审计通过项 (26 项)
- 风控 Validator 链架构: 11 个独立 Validator + 可插拔设计 + fail-fast (优秀)
- VaR/CVaR/Sortino/Calmar 风险度量集成
- 阶梯式熔断(3 级)+ 凯利公式仓位 + 板块集中度检查
- IBKR 连接管理 + 指数退避 + 白名单安全
- AI 投票超时 120s + 弃权机制 + 否决逻辑
- 策略引擎 8 策略 + QuantStats 回测 + 信号预测回验
- 持仓监控 + 观察列表 + 收益报告 + 大盘监控
- 模拟 vs 实盘安全阀 + 多账户隔离

### 技术债 (10 项 — 登记 HEALTH.md)
- IBKR 预算 read-modify-write 非原子 / market_value 字段名误导
- IBKR 失败静默降级模拟盘(幽灵持仓) / 时间止损 datetime 混合
- 做空止损预警缺失 / confirm_proposal 不计日交易数
- reset_budget 硬编码 $2000 / 恢复持仓 entry_time 可能丢失
- /ibuy /isell 绕过 Pipeline / invest_tools datetime 混合

### 文件变更
- `packages/clawbot/src/broker_bridge.py` — 消除 connect() 递归死锁
- `packages/clawbot/src/trading_pipeline.py` — DecisionValidator 异常时 fail-closed
- `packages/clawbot/src/auto_trader.py` — 风控失败跳过候选而非绕过
- `packages/clawbot/src/ai_team_voter.py` — 异常票标记 abstained=True

---

## 2026-04-19 — R7 macOS 业务页面审计（40 条目 / 6 修复 / 20 技术债）
> 领域: `frontend`
> 影响模块: `OrderBook`, `DepthChart`, `KlineChart`, `Money`, `Memory`
> 关联问题: R7 HI-558~563

### R7 macOS 业务页面审计 (40 条目 / 6 修复)
1. **OrderBook Mock 数据清理 (HI-558)**: 移除 basePrice=150 硬编码 Mock，改为空态 + 错误提示
2. **DepthChart Mock 数据清理 (HI-559)**: 同上，移除虚假深度图数据
3. **KlineChart 变量名冲突 (HI-560)**: `setInterval` 覆盖全局函数 → 重命名为 `timeInterval`
4. **交易控制乐观更新回滚 (HI-561)**: 请求失败时恢复开关旧状态
5. **记忆统计总数 BUG (HI-562)**: `entries.length`(分页数) → `memoryStats.total`(真实总数)
6. **OrderBook maxTotal 空数组保护 (HI-563)**: `Math.max(...[])` → `Math.max(1, ...)`

### 技术债 (20 项 — 登记 HEALTH.md)
- 风险参数硬编码 / 无买入流程 / tradingSell 不检查 resp.ok / DevPanel 整个是空壳
- 日志无脱敏机制 / 搜索无高亮 / 两套日志数据源割裂
- 社媒日历无可视化组件 / 人设管理无 UI / Autopilot 用原生 confirm
- 记忆无筛选器 / 进化时间线缺失 / 模型切换需重启 / Token CRUD 不完整 / 调度器无创建编辑

### 文件变更
- `apps/openclaw-manager-src/src/components/Money/OrderBook.tsx` — Mock 清理 + 空态 + maxTotal 保护
- `apps/openclaw-manager-src/src/components/Money/DepthChart.tsx` — Mock 清理 + 空态
- `apps/openclaw-manager-src/src/components/Money/KlineChart.tsx` — interval → timeInterval
- `apps/openclaw-manager-src/src/components/Money/index.tsx` — 控制开关失败回滚
- `apps/openclaw-manager-src/src/components/Memory/index.tsx` — 统计总数优先用后端真实值

---

## 2026-04-19 — R6 macOS 核心页面审计（45 条目 / 8 修复 / 15 技术债）
> 领域: `frontend`
> 影响模块: `conversationService`, `AssetDistribution`, `RecentActivity`, `Assistant`, `Store`, `Channels`
> 关联问题: R6 HI-550~557

### R6 macOS 核心页面审计 (45 条目 / 8 修复)
1. **SSE 超时修复 (HI-550)**: AI 对话 SSE 流式请求从 30s 默认超时改为无超时（`timeoutMs: 0`）
2. **Mock 数据清理 (HI-551)**: AssetDistribution 移除 3 处硬编码假资产数据，改为空态展示 + 错误提示
3. **Mock 数据清理 (HI-552)**: RecentActivity 移除虚假活动列表（买入AAPL等），改为空态展示
4. **滚动优化 (HI-553)**: 流式消息追加时不再强制拉回底部，仅在用户已处于底部时自动滚动
5. **Markdown 链接 (HI-554)**: 行内解析器新增 `[text](url)` 链接支持
6. **会话 CRUD toast (HI-555)**: 4 处 catch 块从仅 console.error 改为 toast.error 用户可见提示
7. **Store 背景修复 (HI-556)**: `bg-[#0D0F14]` 硬编码改为 `bg-[var(--bg-primary)]`，浅色模式适配
8. **Channels 空状态 (HI-557)**: 零频道时展示友好空态提示而非空白

### 技术债 (15 项 — 登记 HEALTH.md)
- 模式切换不传递给后端 / 会话重命名缺失 / 删除无确认
- Bot 详情页缺失 / SERVICE_META 硬编码 / LLM 模型列表硬编码
- 运营设置脏状态检测缺失 / Store 静默降级 / 跟随系统主题缺失
- 频道无新建删除 / 无实时连接状态 / Onboarding 无跳过按钮
- Markdown 图片/有序列表/表格不支持

### 文件变更
- `apps/openclaw-manager-src/src/services/conversationService.ts` — SSE 超时禁用 + CRUD toast
- `apps/openclaw-manager-src/src/components/Dashboard/AssetDistribution.tsx` — Mock 数据清理 + 空态 + 定时刷新
- `apps/openclaw-manager-src/src/components/Dashboard/RecentActivity.tsx` — Mock 数据清理 + 空态
- `apps/openclaw-manager-src/src/components/Assistant/index.tsx` — 智能滚动 + Markdown 链接
- `apps/openclaw-manager-src/src/components/Store/index.tsx` — 背景修复 + 降级提示
- `apps/openclaw-manager-src/src/components/Channels/index.tsx` — 空状态组件

---

## 2026-04-19 — R3+R4+R5 三轮审计（120 条目 / 5 修复 / 19 技术债）
> 领域: `backend`, `frontend`, `docs`
> 影响模块: `callback_mixin`, `help_mixin`, `workflow_mixin`, `config.rs`, `tauri-core.ts`, `COMMAND_REGISTRY.md`
> 关联问题: R3 HI-529~534, R4 HI-535~542, R5 HI-543~549

### R3 Bot 命令层审计 (45 条目 / 3 修复)
1. **回调→命令崩溃修复 (HI-532)**: 新增 `_safe_cmd_from_callback()` 保护 5 处调用
2. **帮助文本修正 (HI-533)**: /invest "5 位 AI" → "6 位 AI"
3. **返回类型一致性 (HI-534)**: `_pick_workflow_bot()` 兜底返回字符串→元组
4. **COMMAND_REGISTRY.md 9 项文档修正**

### R4 Bot 业务场景审计 (40 条目 / 32 通过 / 8 技术债)
- 闲鱼 8/8 全通过 + Kiro Gateway 4/4 全通过 + 投资全链路完整
- 技术债: AI 投票独立追踪/yfinance 缓存降级/freqtrade 死代码/社媒适配器模式/双草稿系统/双价格引擎/ticker 误识别/通知无 flush

### R5 macOS 桌面端架构审计 (35 条目 / 2 修复)
5. **Rust panic 修复 (HI-548)**: `generate_token()` 的 `.expect()` → `if let Err` 降级方案
6. **前端超时修复 (HI-549)**: `clawbotFetch()` 新增 30s AbortController 超时 + `LONG_TIMEOUT_MS` 导出
- Tauri 2 配置 8/8 全通过（CSP/DevTools/权限模型/Vite 配置）
- 97 个 IPC 命令 + 23 页面路由 + 3 层 ErrorBoundary 架构优秀

### 文件变更
- `packages/clawbot/src/bot/cmd_basic/callback_mixin.py` — 新增 `_safe_cmd_from_callback()` + 保护所有回调→命令调用
- `packages/clawbot/src/bot/cmd_basic/help_mixin.py` — 修正 /invest 描述 5→6 位 AI
- `packages/clawbot/src/bot/workflow_mixin.py` — 修正 `_pick_workflow_bot()` 返回类型一致性
- `docs/registries/COMMAND_REGISTRY.md` — 9 项文档修正
- `docs/status/HEALTH.md` — 新增 HI-529~534

---

## 2026-04-18 — T2+T3: 意图识别准确率提升 + 风控系统 BUG 修复
> 领域: `backend`, `trading`
> 影响模块: `chinese_nlp_mixin`, `intent_parser`, `freqtrade_bridge`, `brain_exec_invest`, `risk_manager`
> 关联问题: 四阶段方法论 T2/T3, HI-520, HI-521, HI-522~524

### 变更内容

**T2: 意图识别准确率提升**
1. **正则层扩充**: 新增"走势"→chart、"帮我查/查一下/看下"→ta、autotrader_status 模式
2. **购物消歧修复**: 排除词 `手` 改为 `\d+手` — 修复"入手"中"手"被误杀导致"入手苹果"无法触发购物
3. **dispatch_map 补充**: autotrader_start/stop/status 三个命令补入分发映射
4. **LLM prompt 优化**: 补全 11 类型 + 5 条 few-shot 示例，改善 LLM 降级分类准确率
5. **购物排除模式扩展**: 新增 AMZN/META/BTC/比特币/茅台/特斯拉/英伟达等金融标的排除
6. **测试覆盖提升**: 新增 12 个测试用例覆盖走势/查询/autotrader/购物消歧场景

**T3: 风控系统 BUG 修复**
7. **freqtrade_bridge 修复 (HI-520)**: `confirm_trade_entry()` 传 dict 改为关键字参数 + `.get("approved")` 改为 `.approved` 属性 + 补传默认 3% 止损
8. **brain_exec_invest 修复 (HI-521)**: `_exec_risk_check()` 两处 `check_trade()` 调用补传 `stop_loss=entry_price*0.97`，修复 StopLossValidator 拒绝所有 BUY 交易的问题
9. **架构问题登记 (HI-522~524)**: check_trade() 共享状态竞态、SELL 方向风控缺失、新账户 VaR 空白 — 登记为技术债

### 文件变更
- `packages/clawbot/src/bot/chinese_nlp_mixin.py` — 正则扩充 + 购物消歧修复 + dispatch_map 补充
- `packages/clawbot/src/core/intent_parser.py` — LLM prompt 优化（11类型+few-shot）+ 购物排除模式扩展
- `packages/clawbot/tests/test_message_mixin.py` — 新增 12 个测试用例
- `packages/clawbot/src/freqtrade_bridge.py` — 修复 confirm_trade_entry() API 不匹配
- `packages/clawbot/src/core/brain_exec_invest.py` — 补传 stop_loss 参数修复 StopLossValidator 误拒
- `docs/status/HEALTH.md` — 新增 HI-520~524

---

## 2026-04-18 — T4+T5: QuantStats 报告活化 + LiteLLM 配置外化
> 领域: `backend`, `ai-pool`
> 影响模块: `backtester_vbt`, `cmd_trading_mixin`, `risk_var`, `litellm_router`, `llm_routing_config`, `llm_routing.json`
> 关联问题: 四阶段方法论 T4/T5

### 变更内容

**T4: QuantStats HTML 报告活化**
1. **generate_quantstats_report() 重构**: 从孤儿方法升级为实际可用功能 — 支持全8策略信号生成 + SPY 基准对比 + 接受任意 returns Series
2. **自研引擎接入**: 在 `/backtest` 单股回测路径中新增 `_send_quantstats_report()` — 从 PerformanceReport.daily_returns 生成 HTML tearsheet 并通过 Telegram send_document() 发送
3. **死代码清理**: `risk_var.py` 中 calc_var()/calc_cvar() 的 QuantStats 调用被 numpy 覆盖的死代码已移除

**T5: LiteLLM 配置外化（JSON 为单一真相源）**
4. **Router 参数从 JSON 读取**: `initialize()` 从 JSON `router_config` 字段读取 num_retries/timeout/cooldown 等参数，替代硬编码常量
5. **BOT_MODEL_FAMILY 从 JSON 加载**: 新增 `_load_bot_model_family()` 从 JSON `bot_model_family` 加载 Bot→模型族映射
6. **MODEL_RANKING 移入 JSON**: 50+ 模型评分集中到 JSON `model_ranking` 字段，Python 端动态加载
7. **smart_route 映射移入 JSON**: `_smart_route()` 的 model→family 映射移入 JSON `smart_route_model_to_family` 字段
8. **配置加载器扩展**: `llm_routing_config.py` 新增 `get_model_ranking()` / `get_smart_route_mapping()`

### 文件变更
- `packages/clawbot/src/modules/investment/backtester_vbt.py` — 重构 generate_quantstats_report() + 新增 _get_strategy_signals()
- `packages/clawbot/src/bot/cmd_trading_mixin.py` — 新增 _send_quantstats_report() + 自研引擎接入
- `packages/clawbot/src/risk_var.py` — 清理 calc_var()/calc_cvar() 死代码
- `packages/clawbot/src/litellm_router.py` — Router 参数/BOT_MODEL_FAMILY/MODEL_RANKING/smart_route 从 JSON 加载
- `packages/clawbot/src/llm_routing_config.py` — 新增 get_model_ranking()/get_smart_route_mapping()
- `packages/clawbot/config/llm_routing.json` — 新增 model_ranking/smart_route_model_to_family + 修正 bot_model_family

---

## 2026-04-17 — CSO 全量安全审计修复 (10项)
> 领域: `backend`, `infra`, `frontend`, `deploy`
> 影响模块: `weekly_report`, `xianyu.py`, `docker-compose.yml`, `Makefile`, `deploy_server.py`, `docker-compose.newapi.yml`, `openclaw-manager-src`, `App.tsx`, `Store/index.tsx`, `.env`
> 关联问题: CSO 安全审计 2026-04-17

### 变更内容

**🔴 CRITICAL 修复 (4项)**
1. **周报导入路径修复**: `weekly_report.py` 中 `from src.content_pipeline import ...` 导入路径错误（模块位于 `src.execution.social.content_pipeline`），导致周报生成必然崩溃。修正为正确路径
2. **闲鱼路由 XianyuBot 幻影导入修复**: `api/routers/xianyu.py` 导入不存在的 `XianyuBot` 类，替换为 `XianyuContextManager` 直接查询 SQLite，消除启动时 ImportError
3. **Docker 资源超配修复**: `docker-compose.yml` Redis 内存限制 512M→128M、OpenClaw 主服务 2G→1G，防止 OOM killer 干掉容器；移除 `internal: true` 网络标记恢复容器互联网访问；新增双网络架构（公网+内网隔离）
4. **Makefile Python 路径修复**: 硬编码 `/usr/bin/python3` 在 macOS/brew 环境下不存在，改为 `which python3 || which python` 自动检测

**🟠 HIGH 修复 (3项)**
5. **部署服务器时序攻击修复**: `deploy_server.py` Webhook 签名验证使用 `==` 字符串比较存在时序攻击漏洞，改为 `hmac.compare_digest()` 常量时间比较
6. **NewAPI Docker 安全加固**: `docker-compose.newapi.yml` 添加 `cap_drop: ALL` + `security_opt: no-new-privileges:true`，最小权限原则
7. **移除未使用依赖**: `openclaw-manager-src` 前端项目移除未使用的 `sucrase` 依赖，减少供应链攻击面

**🟡 MEDIUM 修复 (3项)**
8. **误导注释修复**: `App.tsx` 中注释与实际代码行为不符，修正为准确描述
9. **forwardRef 警告修复**: `Store/index.tsx` 中 `PluginCard` 组件触发 React forwardRef 废弃警告，修复组件定义
10. **.env 文件权限加固**: 所有 `.env` 文件权限设置为 `600`（仅 owner 可读写），防止同机其他用户读取密钥

### 文件变更
- `packages/clawbot/src/execution/weekly_report.py` — 修正 content_pipeline 导入路径
- `packages/clawbot/src/api/routers/xianyu.py` — 替换 XianyuBot 为 XianyuContextManager 直接查询
- `docker-compose.yml` — 资源限制调整 + 网络架构重构 + 移除 internal 标记
- `Makefile` — Python 路径自动检测
- `packages/clawbot/src/deployer/deploy_server.py` — hmac.compare_digest 替换 ==
- `docker-compose.newapi.yml` — 安全加固 cap_drop/no-new-privileges
- `apps/openclaw-manager-src/package.json` — 移除 sucrase 依赖
- `apps/openclaw-manager-src/src/App.tsx` — 修正误导注释
- `apps/openclaw-manager-src/src/components/Store/index.tsx` — 修复 forwardRef 警告
- `config/.env*` — 权限收紧为 600

---

## 2026-04-17 — 全量端到端审计 (Sprint 4 审计)

### backend
- **[修复]** yfinance 价格回退：IBKR 离线时自动通过 yfinance 获取实时报价 `rpc.py`
- **[修复]** portfolio-summary 字段映射：qty→quantity, avg_cost→avg_price `trading.py`
- **[修复]** 速率限制提高至 300 req/min `server.py`
- **[新增]** 闲鱼路由: conversations/qr 端点 `routers/xianyu.py`
- **[新增]** WebSocket 事件类型: NOTIFICATION/SERVICE_CHANGE `schemas.py`
- **[修复]** CI 测试断言修复 (Sortino/TailRatio 兼容 quantstats) `test_risk_var.py`

### frontend
- **[修复]** Portfolio 崩溃：avg_cost/avg_price 字段映射 + .toFixed() 安全兜底
- **[修复]** 总市值自动计算 (后端无 total_market_value 字段时从 positions 聚合)
- **[修复]** Store 安装持久化至 localStorage，移除 window.confirm()
- **[修复]** 闲鱼开关接入 serviceStart/serviceStop 真实 API
- **[修复]** 社媒平台数据映射 (数组→对象, xhs/x 名称)
- **[修复]** 死按钮修复 (设置/AI助手使用/发布反馈)
- **[优化]** MOCK_PLUGINS → CURATED_PLUGINS，Evolution 数据优先
- **[优化]** console.error → createLogger 结构化日志
- **[新增]** Onboarding 向导、ErrorState 组件、useClawbotWS hook
- **[新增]** Markdown h1/h2/h3 标题渲染
- **[优化]** AI 模型标签 "Claude 助手" → "AI 助手"

### infra
- **[构建]** Tauri 重新构建并安装至 /Applications/OpenClaw.app
- **[CI]** GitHub Actions CI 通过 (1339 passed)

---

## [2026-04-17] 后端 API 新增 + 前端真实数据对接 — 从演示数据到可用系统
> 领域: `backend`, `frontend`
> 影响模块: `api/routers/system`, `api/routers/trading`, `api/server`, `api/routers/conversation`, `tauri.ts`, `Home`, `conversationService`
> 关联问题: 桌面 APP 5 个页面需要从模拟数据切换到后端真实数据
### 变更内容
- **后端新增 4 组 API 端点** — `GET /api/v1/system/daily-brief`（今日简报聚合 metrics + 模块状态）、`GET/POST /api/v1/system/notifications`（通知列表+标记已读+全部已读）、`GET /api/v1/trading/portfolio-summary`（持仓聚合摘要）、`GET /api/v1/system/services`（服务运行状态检测）
- **挂载 Conversation 路由** — `router_conversation` 之前已实现（SSE 流式对话 333 行），但未在 server.py 注册，导致 /api/v1/conversation/* 端点全部 404
- **前端 tauri.ts 新增全部 API 封装** — dailyBrief/notifications/markNotificationRead/markAllNotificationsRead/portfolioSummary/services/serviceStatus + conversation 完整封装（sessions/create/get/delete/send）
- **Home 首页对接真实数据** — 模拟通知替换为 `api.notifications()` + 首页摘要并行请求加入 `api.dailyBrief()`
- **conversationService SSE 修复** — 流式请求从裸 fetch 改为 clawbotFetch（携带 API Token），修复未授权错误
- **回归测试**: 1339 passed, 2 skipped, 0 failures ✓
### 文件变更
- `packages/clawbot/src/api/server.py` — 新增 router_conversation 导入和挂载（2处）
- `packages/clawbot/src/api/routers/system.py` — 31行→~280行，新增 daily-brief/notifications/services 三组端点
- `packages/clawbot/src/api/routers/trading.py` — 151行→~240行，新增 portfolio-summary 端点
- `apps/openclaw-manager-src/src/lib/tauri.ts` — 719行→~820行，新增所有 API 封装函数
- `apps/openclaw-manager-src/src/components/Home/index.tsx` — 模拟通知→真实 API + dailyBrief 数据对接
- `apps/openclaw-manager-src/src/services/conversationService.ts` — SSE fetch→clawbotFetch + 移除废弃 API_BASE

---


...

查看完整记录请访问 [2026-04.md](CHANGELOG/2026-04.md)
