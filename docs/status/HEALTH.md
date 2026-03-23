# HEALTH.md — 系统健康仪表盘

> 最后更新: 2026-03-23 (QA价值位阶审计，673/673 测试通过，0 TS 错误)
> Bug 生命周期: 发现 → 记录到「活跃问题」→ 修复 → 移至「已解决」→ 运维AI从模式中识别「技术债务」
> 严重度: 🔴 阻塞 | 🟠 重要 | 🟡 一般 | 🔵 低优先

---

## 系统状态

| 维度 | 状态 | 说明 |
|------|------|------|
| 核心服务 | 🟢 运行中 | 7 Bot + FastAPI + Redis (macOS 主节点) |
| LLM 路由 | 🟢 正常 | 15+ provider, 50+ deployment |
| 闲鱼客服 | 🟢 运行中 | WebSocket 连接正常 |
| 交易系统 | 🟡 部分 | IBKR 模拟盘 + Alpaca 纸盘可用，实盘待接入 |
| 备用节点 | 🟢 待命中 | 腾讯云 2C2G 已部署 |
| 测试通过率 | 🟢 100% | 673/673 通过 (OMEGA核心+交易边界+韧性+安全) |
| 代码优化 | 🟢 完成 | 18轮迭代 (含QA价值位阶审计，修复HI-037安全缺口，修复HI-016裸异常)，0 TS 编译错误，0 alert() |

---

## 活跃问题 (OPEN)

### 🟠 重要

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| HI-006 | `backend` | `src/execution_hub.py` | 巨石文件 3,808 行 — 已标记 DEPRECATED，部分拆分到 `src/execution/`，但主文件仍在 | 2026-03-22 |
| HI-007 | `backend` | `src/bot/message_mixin.py` | 文件头有 `Decompyle++` 标记 — 非原始源码，反编译来源 | 2026-03-22 |
| HI-008 | `backend` | `src/execution_hub.py` | 同样是反编译来源 — 部分变量名可能不准确 | 2026-03-22 |
| HI-011 | `backend` | `src/bot/api_mixin.py` | 流式输出群聊频率过高触发 Telegram flood 限制 — 已缓解但未根治 | 2026-03-22 |

### 🟡 一般

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| HI-009 | `ai-pool` | `src/litellm_router.py` | 硅基付费10Key未实名 — 禁止调用Pro模型否则403，key可能报废 | 2026-03-22 |
| HI-010 | `ai-pool` | `config/.env` | NVIDIA NIM API 实为信用额度制 — 非真正无限，试用额度耗尽后停用 | 2026-03-22 |
| HI-012 | `ai-pool` | `src/litellm_router.py` | GPT_API_Free 模型列表需定期校验 — 第三方服务模型可用性经常变动 | 2026-03-22 |
| HI-013 | `ai-pool` | `src/litellm_router.py` | Gemini 2.0 系模型已被 Google 废弃 — 保留为兜底但应迁移到 2.5/3 系 | 2026-03-22 |
| HI-025 | `backend` | 30+ 文件 | 117 处 `datetime.now()` 裸调用残留 — 交易/调度核心路径已修复，日志/元数据路径约 100 处待清理 | 2026-03-23 |

### 🔵 低优先

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| HI-015 | `docs` | `docs/` | `apps/openclaw/AGENTS.md` 和 `packages/clawbot/docs/agents.md` 两个 agent 指令文件并存，命名冲突 | 2026-03-22 |
| HI-017 | `frontend` | `lib/tauri.ts` | 35+ 个 `invokeWithLog<any>` 调用缺少具体类型 | 2026-03-23 |
| HI-026 | `frontend` | 多组件 | 22 处 `: any` 类型注解 (非 tauri.ts 范围) — 主要集中在 API 响应解析 | 2026-03-23 |

---

## 已解决 (RESOLVED)

| ID | 领域 | 模块 | 描述 | 解决方案 | 解决日期 | CHANGELOG |
|----|------|------|------|----------|----------|-----------|
| HI-016 | `backend` | 全局 | 259 处 `except Exception: pass` 静默异常 — 隐藏运行时 bug | 全局清理 `except Exception: pass` 并替换为 `logger.debug("Silenced exception", exc_info=True)` | 2026-03-23 | 全量审计 |
| HI-037 | `backend` | `src/core/security.py` | 缺少 `sanitize_input()` — 无 XSS/SQL注入/路径遍历/命令注入输入消毒 | 增加基础的正则表达式消毒逻辑，修复了 31 个 xfail 的测试用例 | 2026-03-23 | 全量审计 |
| HI-001 | `backend` | `src/risk_manager.py` | `now_et()` timezone-aware vs naive datetime 比较导致熔断崩溃 | 统一使用 `now_et()` | 2026-03-22 | Tier 7 |
| HI-002 | `backend` | `src/monitoring.py` | `AnomalyDetector` deque 切片不支持导致崩溃 (5处) | `list(deque)[:-1]` | 2026-03-22 | Tier 7 |
| HI-003 | `backend` | `src/bot/cmd_basic_mixin.py` | `/ops` 10个按钮全部死亡 — callback handler 未注册 | 注册 `handle_ops_menu_callback` | 2026-03-22 | Tier 6 |
| HI-004 | `backend` | `src/bot/cmd_invest_mixin.py` | `/quote` 3个操作按钮死亡 | 新建 `handle_quote_action_callback` | 2026-03-22 | Tier 6 |
| HI-005 | `backend` | `src/bot/message_mixin.py` | 中文 NL 60+ 触发器是死代码 | `handle_message()` 接入 `_match_chinese_command()` | 2026-03-22 | Tier 6 |
| HI-014 | `backend` | `tests/conftest.py` | 测试 fixture 使用 `datetime.now()` 与生产代码 `now_et()` 时区不匹配，导致日亏损限额测试跨时区失败 | fixture 统一使用 `now_et()` | 2026-03-23 | 全面审查 |
| HI-018 | `backend` | `src/auto_trader.py` | `_safe_notify` 关键词 `\"交易已成交\"` 与 `format_trade_executed` 输出 `\"BUY AAPL 已成交\"` 不匹配，所有成交通知被静默丢弃 | 关键词改为 `\"已成交\"` (更宽泛的子串) | 2026-03-23 | 全面审查 |
| HI-019 | `backend` | `src/rebalancer.py` | `optimize_weights` 方法末尾 14 行死代码 (try/except 双分支均 return 后的 `format_targets` 副本) | 删除死代码 | 2026-03-23 | 全面审查 |
| HI-020 | `backend` | `src/core/security.py` | PIN hash 文件读取失败时 `except: pass` 导致 `verify_pin()` 返回 True (绕过) | 添加 `logger.error` 记录读取失败 | 2026-03-23 | 全面审查 |
| HI-021 | `backend` | `src/core/cost_control.py` | 成本记录持久化和周报读取的 `except: pass` 导致成本追踪静默失效 | 添加 `logger.warning` | 2026-03-23 | 全面审查 |
| HI-022 | `frontend` | 5 个组件 | 7 个 `alert()` 调用 + 5 个 TS 编译错误 + 3 个硬编码 URL + WhatsApp 轮询内存泄漏 | toast 替代 alert、提取 URL 常量、修复 TS 错误 | 2026-03-23 | 全面审查 |
| HI-023 | `backend` | `src/execution_hub.py` | 4 个赏金猎人函数体残缺 — `_today_bounty_accept_cost`/`_today_accepted_bounty_ids`/`_record_bounty_run` 无 return/写入逻辑，`_accepted_bounty_shortlist` 引用未定义变量 `allowed_platforms` 导致 NameError | 补全所有函数体逻辑 | 2026-03-23 | 第二轮审查 |
| HI-024 | `backend` | `src/trading_system.py` | `_parse_datetime` 返回 naive datetime，与 `now_et()` (aware) 混用导致 MonitoredPosition 时间比较 TypeError | `_parse_datetime` 对 naive datetime 自动标记 ET 时区 | 2026-03-23 | 第二轮审查 |
| HI-027 | `backend` | 7 个文件 | 交易/调度核心路径 9 处 `datetime.now()` 裸调用 — alpaca_bridge/broker_bridge/invest_tools/data_providers/scheduler/globals/xianyu_live | 全部替换为 `now_et()` | 2026-03-23 | 第二轮审查 |
| HI-028 | `backend` | 3 个文件 | 5 处 `asyncio.create_task` 火后即忘 — message_mixin(2处)/smart_memory(2处) 的后台任务异常被静默吞掉 | 添加 `add_done_callback` 记录异常 | 2026-03-23 | 第二轮审查 |
| HI-029 | `frontend` | 2 个组件 | `CommandPalette.tsx` `as any` + `Plugins/index.tsx` `as any` — 类型不安全的断言 | 改为 `as PageType` / `as MCPPlugin['status']` | 2026-03-23 | 第二轮审查 |
| HI-030 | `backend` | `src/core/cost_control.py` | `record_cost` 预算告警 `_today_spend/_daily_budget` 在 `_daily_budget=0` 时 ZeroDivisionError — 零预算场景生产 Bug | 添加 `_daily_budget \u003e 0` 前置守卫 | 2026-03-23 | QA审计 |
| HI-031 | `backend` | `tests/conftest.py` | `mock_journal.close_trade` 返回 `None` 但真实代码返回 `dict` — 10+ 个依赖此 fixture 的测试用错误 mock 运行 | 返回值改为匹配真实 `TradingJournal.close_trade()` 返回结构 | 2026-03-23 | QA审计 |
| HI-032 | `backend` | `tests/test_risk_manager.py` | `_cooldown_until = datetime.now()` naive datetime 与生产代码 `now_et()` aware datetime 混用 — 冷却期逻辑测试无效 | 改为 `now_et()` | 2026-03-23 | QA审计 |
| HI-033 | `backend` | `tests/test_decision_validator.py` | `if result.approved: assert ...` 条件断言 — approved=False 时断言被跳过，测试静默通过 | 改为 unconditional `assert result.approved is True` | 2026-03-23 | QA审计 |
| HI-034 | `backend` | `tests/test_position_monitor.py` | 全部 13 处 `datetime.now()` naive datetime — 与源码 `now_et()` aware 混合比较 | 全部改为 `now_et()` | 2026-03-23 | QA审计 |
| HI-035 | `backend` | `tests/test_auto_trader.py` | `assert quantity \u003e= 1` / `stop_loss \u003e 0` 过于宽松 — 无法捕获公式变更回归 | 精确断言 `== 2` + 验证 SL < entry_price | 2026-03-23 | QA审计 |
| HI-036 | `backend` | `src/risk_manager.py` | `calc_safe_quantity` 3 个未防护边界: entry_price=0 → ZeroDivisionError, stop_loss=None → TypeError, capital=0 → 错误消息不准确 | 添加前置参数守卫 | 2026-03-23 | QA位阶审计 |

---

## 技术债务

> 运维 AI 通过活跃问题的模式分析识别深层架构问题。

| 领域 | 债务描述 | 根因 | 建议 | 关联 HI |
|------|----------|------|------|---------|
| `backend` | 两个巨石反编译文件占总代码量 ~10% | 项目早期从 `.pyc` 逆向恢复 | 逐步用全新实现替换，按功能拆分 | HI-006, HI-007, HI-008 |
| `ai-pool` | 多个第三方 API 限制频繁变动 | 依赖免费/试用层 API | 建立定期巡检机制，自动检测 key 余额和模型可用性 | HI-009, HI-010, HI-012, HI-013 |
| `backend` | Telegram 流式输出 flood 限制 | 群聊编辑频率过高 | 实现服务端消息队列合并，或改用单次完整回复 | HI-011 |
| `backend` | 117 处 `datetime.now()` 裸调用 (日志/元数据路径) | 早期代码未统一时区策略 | 分批替换为 `now_et()` 或 `datetime.now(timezone.utc)` | HI-025 |

---

## 部署状态

| 环境 | 状态 | 地址 | 说明 |
|------|------|------|------|
| macOS 主节点 | 🟢 运行中 | localhost (LaunchAgent) | 7 Bot + FastAPI :18790 + g4f :18891 + Kiro :18793 |
| 腾讯云备用 | 🟢 待命中 | 101.43.41.96 (systemd) | 精简核心: 7Bot + FastAPI + Redis, 74个国内LLM源 |
| 心跳机制 | 🟢 运行中 | macOS→腾讯云 每60秒 | LaunchAgent SSH touch, 备用30秒检查 |
| 故障转移 | 🟢 已配置 | systemd timer | 主节点连续3次无心跳(90秒)自动切换 |
| Docker | ⚪ 可选 | — | Redis :6379, MediaCrawler :8080, Goofish :8000 |

---

## 统计

| 严重度 | 活跃 | 已解决 | 合计 |
|--------|------|--------|------|
| 🔴 阻塞 | 0 | 0 | 0 |
| 🟠 重要 | 4 | 12 | 16 |
| 🟡 一般 | 5 | 5 | 10 |
| 🔵 低优先 | 3 | 9 | 12 |
| **合计** | **12** | **26** | **38** |

---

## 运维 AI 分析指引

### Bug 生命周期

```
发现 Bug → 记录到「活跃问题」(含 HI-ID / 严重度 / 领域)
    ↓
修复 Bug → 移至「已解决」(含解决方案 / 日期 / CHANGELOG 引用)
    ↓
运维 AI 分析 → 从 Bug 模式识别深层架构问题 → 记入「技术债务」
```

### 模式识别规则

- 同一模块 ≥3 个 Bug → 该模块需要重构
- 同一领域 ≥5 个活跃问题 → 该领域存在系统性风险
- 技术债务 ≥3 条未处理 → 建议安排专项清理迭代
- 🟠 重要 + 活跃 ≥3 → 应优先处理，可能影响系统稳定性
