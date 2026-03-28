# HEALTH.md — 系统健康仪表盘

> 最后更新: 2026-03-29 (R22深度审计清理: 15个死文件+38个未使用import+28个死代码单元+17个重复函数合并 | 1046/1046 passed)
> Bug 生命周期: 发现 → 记录到「活跃问题」→ 修复 → 移至「已解决」→ 运维AI从模式中识别「技术债务」
> 严重度: 🔴 阻塞 | 🟠 重要 | 🟡 一般 | 🔵 低优先

---

## 功能优先级矩阵 (CEO 拍板, 2026-03-23)

> 得分公式: 痛点烈度×2 - 技术成本。🚀立即 = 本周启动 | ⏳待定 = 下个迭代

### Phase 1 — 本周必须做

| # | 功能 | 痛点(1-5) | 成本(1-5) | 得分 | 决策 | 关联 HI |
|---|-----|----------|----------|------|------|---------|
| 1 | sanitize_input 安全实现 | 5 | 2 | 8 | 🚀立即 | HI-037 |
| 2 | Telegram flood 根治 | 4 | 3 | 5 | 🚀立即 | HI-011 |
| 3 | execution_hub.py 引用切换完成 | 4 | 4 | 4 | 🚀立即 | HI-006 |

### Phase 2 — 核心价值兑现

| # | 功能 | 痛点(1-5) | 成本(1-5) | 得分 | 决策 | 关联 HI |
|---|-----|----------|----------|------|------|---------|
| 4 | ~~IBKR 实盘接入~~ | 5 | 3 | 7 | ✅ 完成 | — |
| 5 | ~~投资决策→回测→执行闭环~~ | 5 | 2 | 8 | ✅ 完成 | — |
| 6 | 反编译文件重写 (message_mixin 优先) | 4 | 5 | 3 | 🚀立即 | HI-007/008 |

### Phase 3 — 增长引擎

| # | 功能 | 痛点(1-5) | 成本(1-5) | 得分 | 决策 | 关联 HI |
|---|-----|----------|----------|------|------|---------|
| 7 | ~~新手交互式引导~~ | 4 | 2 | 6 | ✅ 完成 | — |
| 8 | ~~社媒一键双平台发文~~ | 4 | 3 | 5 | ✅ 完成 | — |
| 9 | ~~闲鱼底线价自动成交~~ | 3 | 2 | 4 | ✅ 完成 | — |
| 10 | ~~收益可视化曲线~~ | 3 | 2 | 4 | ✅ 完成 | — |

---

## 系统状态

| 维度 | 状态 | 说明 |
|------|------|------|
| 核心服务 | 🟢 运行中 | 7 Bot + FastAPI + Redis (macOS 主节点) |
| LLM 路由 | 🟢 加固 | 多级降级链(qwen→deepseek→g4f) + 流式成本追踪 + 15+ provider |
| 主动智能 | 🟢 运行中 | ProactiveEngine 三步管道 + EventBus触发 + 30min定时检查 |
| AI 记忆 | 🟢 贯通 | SmartMemory→SharedMemory→TieredContextManager user_profile 双通道同步 |
| 意图识别 | 🟢 加固 | 中文NLP→fast_parse正则→LLM降级分类→Brain任务图，三级漏斗 |
| 闲鱼客服 | 🟢 加固 | 底价注入+10msg/min限速+prompt注入防护+自动接受价格上限+后台任务异常监控+库存低预警 |
| 交易系统 | 🟢 安全加固 | 22项安全修复 + 风控参数验证 + 日盈亏锁 + SELL风控 + 预算竞态修复 + AI共识度分歧保护 |
| 备用节点 | 🟡 待命中 | 腾讯云 2C2G — 代码已同步, systemd 服务已创建, failover timer 运行中, 待心跳恢复后自动切换 |
| 测试通过率 | 🟢 100% | 1046/1046 Python (含41项AI助手能力测试), 0 TypeScript错误 |
| 投资信号追踪 | 🟢 贯通 | record_prediction→validate_predictions→vote_history 三管道全通 |
| 社媒数据分析 | 🟢 贯通 | 浏览器采集→post_engagement存储→/social_report展示→PostTimeOptimizer学习 |
| 闲鱼运营智能 | 🟢 加固 | 利润核算修复+转化标记修复+商品排行+时段分析+转化漏斗+库存低预警 |
| 生活自动化 | 🟢 运行中 | 提醒(周期性)+记账(收入/支出/月预算/超支告警/月度聚合)+话费水电费余额追踪+定时低余额告警 |
| 购物比价 | 🟢 加固 | 四级降级比价+降价提醒监控(price_watches)+6h定时检查+中文NLP触发 |
| 代码优化 | 🟢 完成 | 41轮迭代, 全部活跃HI修复, start_trading_system 786→33行, _setup_scheduler 698→48行, 273 个未使用 import 清理 + 6 处 create_task 修复 + 498 处静默异常修复 + 前端 Mock 数据替换 + 11处前端命令命名修复 + 2个死模块接入 + R22深度清理: 15死文件(3.4K行)+38未使用import+28死方法+17重复函数合并 |
| 架构治理 | 🟢 完成 | 全链路: 人格/提示词/装饰器/错误消息/认证/记忆隔离/日志安全/配置校验/备份 |
| API 安全 | 🟢 加固 | X-API-Token + CORS + SSRF + 输入验证 + diagnose=False |
| LLM 安全 | 🟢 加固 | Key脱敏(8字符) + 死Key禁用 + 错误清洗 |
| 前端 | 🟢 修复 | 0 TS错误, Tauri shell权限收窄, CSP启用, 状态同步, 内存泄漏修复, JSON.parse 崩溃防护 + 定时器泄漏修复 + 250 行重复代码消除 + Mock 数据替换为 API 调用 |
| 部署安全 | 🟢 加固 | VPS systemd加固(non-root+沙箱) + .env排除 + LaunchAgent改进 + deploy_server 默认绑定 127.0.0.1 + compose 资源限制 |
| Git 仓库 | 🟢 清理 | 49K 文件从 Git 索引移除 (.venv/node_modules/browser), .gitignore 补充, R21清理24截图+2数据库+残留目录 |
| 数据完整性 | 🟢 加固 | yfinance 60s缓存+新鲜度检测 + 3个DB自动清理(每日03:00) + 9个DB自动备份(每日04:00) + 全部SQLite启用WAL模式 |
| 灾难恢复 | 🟢 就绪 | 自动备份(7日/4周保留) + DR指南 + VPS rsync排除数据库 |
| 通知可靠性 | 🟢 加固 | P0通知3次重试 + 关机刷新批处理 + EventBus异常日志 |

---

## 活跃问题 (OPEN)

### 🔴 阻塞

(无)

### 🟠 重要

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| HI-277 | `deploy` | VPS failover | Mac 恢复后无 VPS 退让机制 — 可能导致双节点同时运行 Bot | 2026-03-27 |
| HI-278 | `deploy` | VPS failover | failover timer 脚本原不在 Git 仓库 — VPS 重装后机制丢失 (已新建 vps_failover_check.sh) | 2026-03-27 |
| HI-348 | `security` | `.openclaw/agents/` | API密钥(Anthropic/OpenAI)曾提交到Git历史 — 已从索引移除但历史仍存在 | 2026-03-28 |
| HI-349 | `security` | `code_tool.py` | Python/Node.js代码沙箱可被CPython内部机制绕过 — 需OS级隔离 | 2026-03-28 |

### 🟡 一般

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| HI-280 | `deploy` | LaunchAgent | macOS 日志累积 185MB 无轮转，需 newsyslog 配置 | 2026-03-27 |
| HI-283 | `frontend` | 多组件 | 21处英文注释 + 5处英文 console 消息违反中文化规范 | 2026-03-27 |
| HI-350 | `backend` | `xianyu_live.py` | 闲鱼app-key硬编码在源码中(非私密但应外部化) | 2026-03-28 |
| HI-358 | `backend` | 多文件 | R22已拆分: cmd_basic_mixin(子包7文件)+risk_config+trading_memory_bridge+broker_selector; 仍有~15个文件>800行待拆 | 2026-03-29 |
| HI-359 | `backend` | `bot/globals.py` | 循环依赖中心 — 与context_manager/shared_memory/history_store互引，需提取纯数据层 | 2026-03-29 |
### 🔵 低优先

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| HI-284 | `backend` | 3个文件 | _emit_flow fallback stub 在 task_graph/execution/_ai/x_platform 重复定义 | 2026-03-27 |

---

## 已解决 (RESOLVED)

| ID | 领域 | 模块 | 描述 | 解决方案 | 解决日期 | CHANGELOG |
|----|------|------|------|----------|----------|-----------|
| HI-363 | `backend` | 全项目 | 深度审计: 15个死文件(3,461行)+38个未使用import+28个死方法/常量(536行)+17个重复函数 | 删除死文件+清理import+删除死方法+合并到规范源 | 2026-03-29 | 深度审计清理 |
| HI-362 | `backend` | 9个bot/core文件 | 22个幻影导入(从globals.py导入不存在的符号) — Bot启动时ImportError崩溃 | 将每个符号重定向到实际定义模块(broker_selector/invest_tools/_lifecycle/ta_engine等) | 2026-03-29 | 幻影导入修复 |
| HI-360 | `backend` | 5个core/文件 | `api_limiter` 在5个consumer文件中重复try/except fallback | 移除冗余fallback，统一为 `from src.resilience import api_limiter` 直接导入 | 2026-03-29 | HI-360修复 |
| HI-282 | `backend` | `litellm_router.py` | 2个废弃方法(remove_exhausted/init_adaptive_router)已清理 | 删除 remove_exhausted() + init_adaptive_router()，multi_main.py 移除调用，添加注释说明已废弃 | 2026-03-28 | 死代码清理 |
| HI-357 | `security` | `.gitignore` | .openclaw/agents/ 和 identity/ 未在.gitignore中排除 | 添加安全敏感目录到.gitignore + git rm --cached移除42个文件 | 2026-03-28 | R13审计 |
| HI-356 | `security` | `life_automation.py` | open_app/run_shortcut接受未验证用户输入(可执行任意应用) | 添加18项安全白名单+快捷指令名称校验 | 2026-03-28 | R13审计 |
| HI-355 | `security` | `deploy_client.py` | cmd.split()替代shlex.split()存在命令注入风险 | 替换为shlex.split(cmd) | 2026-03-28 | R13审计 |
| HI-354 | `backend` | `reentry_queue.py` | dict\|None语法不兼容Python 3.9(CI矩阵包含3.9) | 改为Optional[dict] | 2026-03-28 | R13审计 |
| HI-353 | `backend` | `alpaca_bridge.py` | Mock数据无明确标识,用户可能误认为真实交易数据 | 添加⚠️模拟数据标签+logger.warning | 2026-03-28 | R13审计 |
| HI-352 | `backend` | `multi_main.py` | 关机时subprocess.run阻塞异步事件循环+bots[0].bot属性不存在 | asyncio.to_thread包装+修正为bots[0].app.bot | 2026-03-28 | R13审计 |
| HI-351 | `backend` | `multi_bot.py`, `notify_style.py` | pass后跟logger.debug(6处死代码,日志永远无法记录) | 移除pass,保留logger.debug作为except块体 | 2026-03-28 | R13审计 |
| HI-347 | `backend` | `requirements.txt` | pyautogui/pyobjc在Linux部署时安装失败 | 添加sys_platform=='darwin'条件标记 | 2026-03-28 | R13审计 |
| HI-346 | `frontend` | `App.tsx` | Evolution页面(569行)已实现但未接入路由,用户无法访问 | 添加PageType+lazy import+Sidebar菜单+Header标题 | 2026-03-28 | R13审计 |
| HI-345 | `frontend` | `App.tsx` | CommandPalette(Cmd+K)已实现但未挂载到DOM | 在App主组件中渲染\<CommandPalette/\> | 2026-03-28 | R13审计 |
| HI-361 | `trading` | `position_monitor.py` | SELL方向持仓无止损/止盈/追踪止损/分批止盈 — 做空只靠日亏损熔断 | 实现完整SELL分支: 止损(价格>=SL)、追踪止损(价格>=trailing)、分批止盈(1.5R)、止盈(价格<=TP) + 追踪止损下移逻辑 | 2026-03-28 | R17审计 |
| HI-358 | `backend` | `cmd_social_mixin.py` 等5个文件 | cmd_execution_mixin.py(2602行)已拆分完成 | 移至已解决 | 2026-03-28 | R14审计 |
| HI-344 | `deploy` | VPS | VPS代码过时+pandas依赖缺失+failover状态卡在active | rsync同步最新代码+pip install依赖+重置failover为standby | 2026-03-28 | R12审计 |
| HI-343 | `frontend` | tauri.ts | 34个后端API命令前端未封装,桌面端无法调用 | 补入34个API函数+修正3个参数名 | 2026-03-28 | R12审计 |
| HI-342 | `backend` | cmd_trading_mixin.py | 回测高级功能(蒙特卡洛/参数优化/前进分析)已实现但无用户入口 | /backtest monte/optimize/walkforward 子命令+中文触发词 | 2026-03-28 | R12审计 |
| HI-341 | `backend` | cmd_invest_mixin.py | /buy 交易日志导入路径错误(src.trading.trading_journal),日志静默丢失 | 修正为 src.trading_journal 匹配实际位置 | 2026-03-28 | R12审计 |
| HI-340 | `backend` | cmd_basic_mixin.py | /keyhealth 命令注册但 handler 不存在,触发崩溃 | 实现 cmd_keyhealth 方法(API Key健康验证) | 2026-03-28 | R12审计 |
| HI-339 | `backend` | cmd_analysis_mixin.py | /factors 命令注册但 handler 不存在,触发崩溃 | 实现 cmd_factors 方法(16 Alpha因子分析) | 2026-03-28 | R12审计 |
| HI-338 | `backend` | cmd_analysis_mixin.py | /drl 命令注册但 handler 不存在,触发崩溃 | 实现 cmd_drl 方法(DRL策略分析+优雅降级) | 2026-03-28 | R12审计 |
| HI-337 | `backend` | multi_main.py | init_goofish_monitor从未调用 — 闲鱼监控无法启动 | 在启动流程中接入初始化(try/except保护) | 2026-03-28 | R11审计 |
| HI-336 | `backend` | multi_main.py | init_adaptive_router从未调用 — 自适应路由器形同虚设 | 在启动流程中接入初始化(try/except保护) | 2026-03-28 | R11审计 |
| HI-335 | `frontend` | tauri.ts | 11处前端命令名与后端不匹配(缺_api_前缀) — 桌面端核心面板全部报错 | 统一添加_api_前缀匹配后端注册名 | 2026-03-28 | R11审计 |
| HI-334 | `backend` | 120个文件 | 498处静默吞异常(except无as e且无日志) — 生产环境异常完全无法追溯 | 正则批量修复: 63处pass添加logger.debug + 251处业务代码添加as e + 147处具体异常添加as e + 37处特殊异常添加as e | 2026-03-28 | R11审计 |
| HI-333 | `docs` | AGENTS.md | 开发 SOP 不够系统，用户需代入技术角色 | 升级为 AI CEO SOP (8 阶段完整流水线) | 2026-03-28 | 全量审计R10 |
| HI-332 | `deploy` | requirements.txt | 7 个依赖无版本上界 + 测试依赖混入生产 | 添加上界 + 新建 requirements-dev.txt | 2026-03-28 | 全量审计R10 |
| HI-331 | `deploy` | deploy_server_main.py | 默认绑定 0.0.0.0 暴露公网 | 改为 127.0.0.1 | 2026-03-28 | 全量审计R10 |
| HI-330 | `deploy` | docker-compose.mediacrawler.yml | 缺资源限制和健康检查 | 添加 limits + healthcheck | 2026-03-28 | 全量审计R10 |
| HI-329 | `deploy` | docker-compose.goofish.yml | 注释含默认密码 admin/admin123 + 缺资源限制 | 删除密码 + 添加 limits + healthcheck | 2026-03-28 | 全量审计R10 |
| HI-328 | `deploy` | .gitignore + Git 索引 | .venv(12K)+node_modules(35K)+browser(1.5K) 文件被 Git 跟踪导致仓库 483MB | git rm --cached 清理 + .gitignore 补充 | 2026-03-28 | 全量审计R10 |
| HI-327 | `frontend` | Channels/index.tsx | 约 250 行代码与 channelDefinitions.ts 重复 | 统一从 channelDefinitions.ts 导入 | 2026-03-28 | 全量审计R10 |
| HI-326 | `frontend` | Channels/index.tsx | WhatsApp 登录定时器泄漏 | useRef + useEffect cleanup | 2026-03-28 | 全量审计R10 |
| HI-325 | `frontend` | Social+Money+Memory | 6 处硬编码 Mock 数据误导用户 | 替换为 API 调用 + 空态 UI | 2026-03-28 | 全量审计R10 |
| HI-324 | `frontend` | Memory/index.tsx | JSON.parse 未保护，非法 JSON 导致白屏崩溃 | try-catch 包裹，失败回退原始字符串 | 2026-03-28 | 全量审计R10 |
| HI-323 | `backend` | globals.py | ruff 误删 3 个 re-export (send_long_message/get_stock_quote/execute_trade_via_pipeline) | 恢复 re-export 导入 | 2026-03-28 | 全量审计R10 |
| HI-322 | `backend` | 6 个文件 | 6 处 fire-and-forget create_task 异步异常被静默丢失 | add_done_callback 捕获异常 | 2026-03-28 | 全量审计R10 |
| HI-321 | `backend` | 110 个文件 | 273 处未使用 import (F401) 影响启动速度和代码清洁 | ruff 自动修复 254 + 手动修复 19 | 2026-03-28 | 全量审计R10 |
| HI-320 | `backend` | `life_automation.py` | 周期性提醒首次触发错误地设为5分钟后 — NLP 层不生成 time_text 导致走 delay 降级 | create_reminder 中新增分支: time_text 为空且有 recurrence_rule 时用 _calc_next_occurrence 计算首次触发 | 2026-03-28 | 周期提醒首次触发修复 |
| HI-309 | `trading` | `auto_trader.py` | 投资信号预测从未被记录 — record_prediction() 死代码 | execute_proposal() 中 open_trade 后追加 record_prediction 调用 | 2026-03-27 | 第五轮产品跃迁 |
| HI-310 | `trading` | `trading_system.py` | 收盘复盘不验证AI预测准确率 — validate_predictions() 死代码 | _eod_auto_review() 中追加 validate_predictions 调用 | 2026-03-27 | 第五轮产品跃迁 |
| HI-311 | `trading` | `trading_system.py` | AI投票无历史准确率反馈 — vote_history 从未被传递 | _ai_team_wrapper() 中获取 get_prediction_accuracy 并传入 | 2026-03-27 | 第五轮产品跃迁 |
| HI-312 | `xianyu` | `xianyu_live.py` | record_order() 未传 amount — 利润核算永远为0 | 从商品 SKU/soldPrice 提取价格传入 amount 参数 | 2026-03-27 | 第五轮产品跃迁 |
| HI-313 | `xianyu` | `xianyu_live.py` | mark_converted() 参数传反 — 转化率统计失真 | 交换参数顺序对齐签名 (chat_id, item_id) | 2026-03-27 | 第五轮产品跃迁 |
| HI-314 | `social` | `social_scheduler.py` | 浏览器采集的互动数据不存储 — post_engagement 表永远为空 | job_late_review 中调用 record_post_engagement() | 2026-03-27 | 第五轮产品跃迁 |
| HI-315 | `social` | `content_pipeline.py` | /social_report 空壳 — by_platform/top_posts 字段不存在 | get_post_performance_report() 接入真实互动数据 | 2026-03-27 | 第五轮产品跃迁 |
| HI-316 | `social` | `social_scheduler.py` | KPI 检查路径错误 — result.get("x").get("views") 永远返回0 | 修正为正确的嵌套路径 result["x"]["stats"]["..."] | 2026-03-27 | 第五轮产品跃迁 |
| HI-317 | `social` | `social_tools.py` | PostTimeOptimizer 内存dict重启丢失+每次新建实例 | JSON持久化 + 全局单例 get_post_time_optimizer() | 2026-03-27 | 第六轮产品跃迁 |
| HI-318 | `backend` | `response_synthesizer.py` | 购物比价LLM承诺\"设降价提醒\"但功能不存在 | 移除空头承诺改为\"直接买/再等等/改天再搜\" | 2026-03-27 | 第六轮产品跃迁 |
| HI-319 | `xianyu` | `cmd_execution_mixin.py` | 闲鱼BI三个查询方法无任何用户入口 | /xianyu_report升级+12个中文触发词+日报Top3 | 2026-03-27 | 第六轮产品跃迁 |

| ID | 领域 | 模块 | 描述 | 解决方案 | 解决日期 | CHANGELOG |
|----|------|------|------|----------|----------|-----------|
| HI-305 | `social` | `social_scheduler.py` | job_late_review 采集数据后不存数据库，post_engagement 表永远为空 | 调用 record_post_engagement() 存入 X/XHS 互动数据 | 2026-03-27 | 社媒数据管道修复 |
| HI-306 | `social` | `content_pipeline.py` | get_post_performance_report() 不返回 by_platform/top_posts，/social_report 命令展示空白 | 整合 get_engagement_summary() 真实数据 + DB top_posts 查询 | 2026-03-27 | 社媒数据管道修复 |
| HI-307 | `social` | `social_scheduler.py` | PostTimeOptimizer 无数据源，永远返回默认时段 | job_late_review 中喂入互动率数据 | 2026-03-27 | 社媒数据管道修复 |
| HI-308 | `social` | `social_scheduler.py` | KPI 检查路径错误: result.get("x").get("views") 但实际数据在 result["x"]["stats"] 层 | 修正为 result.get("x",{}).get("stats",{}) | 2026-03-27 | 社媒数据管道修复 |
| HI-280 | `xianyu` | `xianyu_live.py` | record_order() 未传 amount，利润核算永远为 0 | 从商品 SKU/soldPrice 提取价格传入 amount | 2026-03-27 | 闲鱼参数Bug修复 |
| HI-281 | `xianyu` | `xianyu_live.py` | mark_converted() 参数传反，转化标记无效 | 交换参数顺序: mark_converted(uid, item_id) | 2026-03-27 | 闲鱼参数Bug修复 |
| HI-300 | `backend` | `auth.py` | API Token 比较不防时序攻击 | 改用 hmac.compare_digest() | 2026-03-27 | 全量审计R9 |
| HI-301 | `backend` | `monitoring.py` | cost_analytics.db 缺 WAL 模式 | 添加 PRAGMA journal_mode=WAL | 2026-03-27 | 全量审计R9 |
| HI-302 | `backend` | `feedback.py` | 路径硬编码不同工作目录会找错 | Path(__file__).parent 模式 | 2026-03-27 | 全量审计R9 |
| HI-303 | `backend` | `omega.py` | SSRF 172.* 判断过宽误判公网 | ipaddress.is_private 精确判断 | 2026-03-27 | 全量审计R9 |
| HI-276 | `deploy` | VPS | VPS 备用节点完全未部署 | 代码同步+systemd服务+failover timer+心跳恢复 | 2026-03-27 | 全量审计R3 |
| HI-279 | `deploy` | Git | .venv312/+node_modules/ 被 Git 跟踪 (47K文件) | git rm --cached 清理 | 2026-03-27 | 全量审计R3 |
| HI-285 | `xianyu` | `xianyu_context.py` | get_recent_item_id() 查询不存在的 conversations 表，自动发货链路断裂 | 改为查 messages 表 | 2026-03-27 | 全量审计R4 |
| HI-286 | `backend` | `smart_memory.py` | 偏好检测死代码: self.shared_memory不存在+参数错误 | self.memory + 正确参数 | 2026-03-27 | 全量审计R4 |
| HI-287 | `xianyu` | `xianyu_live.py` | record_order() 参数错位 | 改用具名参数 | 2026-03-27 | 全量审计R4 |
| HI-288 | `backend` | `order_notifier.py` | time.sleep() 在异步上下文阻塞事件循环 | 异步场景跳过同步重试 | 2026-03-27 | 全量审计R4 |
| HI-289 | `social` | `social_scheduler.py` | 午间互动两操作共享try块 | 拆分独立try块 | 2026-03-27 | 全量审计R4 |
| HI-261 | `deploy` | `.gitignore` | .venv312/ 未被 .gitignore 排除 (3.1GB 虚拟环境被跟踪) | `.venv/` → `.venv*/` 通配符 | 2026-03-27 | 第49轮全量审计 |
| HI-262 | `deploy` | `.dockerignore` | Docker 镜像包含 config/.env 密钥文件 | 添加 `config/.env` + `*.pem` + `*.key` 排除规则 | 2026-03-27 | 第49轮全量审计 |
| HI-263 | `deploy` | `requirements.txt` | playwright 未列入依赖，VPS/Docker 部署 ImportError | 添加 `playwright>=1.40.0` | 2026-03-27 | 第49轮全量审计 |
| HI-264 | `deploy` | `kiro-gateway/docker-compose.yml` | 端口绑定 0.0.0.0 暴露公网 + 废弃 version 字段 | `127.0.0.1:8000:8000` + 删除 version | 2026-03-27 | 第49轮全量审计 |
| HI-265 | `deploy` | `docker-compose.mediacrawler.yml` | 端口 8080 绑定 0.0.0.0 | `127.0.0.1:8080:8080` | 2026-03-27 | 第49轮全量审计 |
| HI-266 | `deploy` | `docker-compose.goofish.yml` | 端口 8000 绑定 0.0.0.0 | `127.0.0.1:8000:8000` | 2026-03-27 | 第49轮全量审计 |
| HI-267 | `backend` | 6个文件 | asyncio.get_event_loop() 在 Python 3.12 已废弃 (7处) | 统一改用 get_running_loop() 或 asyncio.run() | 2026-03-27 | 第49轮全量审计 |
| HI-268 | `backend` | 4个文件 | fire-and-forget create_task 无异常回调 (4处) | 添加 add_done_callback + logger.debug | 2026-03-27 | 第49轮全量审计 |
| HI-269 | `backend` | `feedback.py` | SQLite 连接无自动关闭机制 | atexit.register(self.close) | 2026-03-27 | 第49轮全量审计 |
| HI-270 | `backend` | `monitoring.py` | CostAnalyzer._init_db() SQLite 缺 timeout 参数 | 添加 timeout=10 | 2026-03-27 | 第49轮全量审计 |
| HI-271 | `backend` | `github_trending.py` | aiohttp.ClientSession() 无默认超时 (3处) | 添加 session 级 timeout 兜底 | 2026-03-27 | 第49轮全量审计 |
| HI-272 | `frontend` | `Memory/index.tsx` | API 返回数据使用 any 类型 | 定义 MemoryApiResult 接口 | 2026-03-27 | 第49轮全量审计 |
| HI-273 | `frontend` | `Plugins/index.tsx` | targetStatus as any 类型断言 | 改为 MCPPlugin['status'] 精确类型 | 2026-03-27 | 第49轮全量审计 |
| HI-274 | `frontend` | `Setup/index.tsx` | setTimeout 未清理，组件卸载后可能操作已销毁组件 | 添加 clearTimeout 清理 | 2026-03-27 | 第49轮全量审计 |
| HI-275 | `frontend` | `Settings/index.tsx` | setTimeout 未清理，同上 | 添加 clearTimeout 返回清理函数 | 2026-03-27 | 第49轮全量审计 |
| HI-258 | `backend` | `bot/__init__.py` | 循环导入: telegram_ux ↔ bot (连锁加载10个Mixin) | 清除 `__init__.py` 中的模块级 `import MultiBot`（无消费者使用此便捷导入） | 2026-03-27 | 第四轮产品跃迁 |
| HI-171 | `deploy` | `heartbeat-sender.plist` | SSH StrictHostKeyChecking=no 中间人攻击风险 | `StrictHostKeyChecking=accept-new` | 2026-03-26 | 基础设施修复 |
| HI-180 | `backend` | `message_mixin.py` 等5个 | 5个 Callback Handler 无用户身份验证，群组内任何人可点击交易/发布按钮 | 每个 handler 添加 `_is_authorized()` 检查 | 2026-03-26 | 第32轮审计 |
| HI-204 | `deploy` | `gateway.plist` | Gateway Token 硬编码在 plist 中，提交 Git 泄露 | 改为占位符 `${OPENCLAW_GATEWAY_TOKEN}` + 注释警告 | 2026-03-26 | 第33轮审计 |
| HI-216 | `backend` | `code_tool.py` | Python 沙箱可通过 object.__subclasses__() 和 open() 绕过 | 禁用 builtins.open + type.__subclasses__ 返回空列表 | 2026-03-26 | 第34轮审计 |
| HI-217 | `backend` | `bash_tool.py` | execute_dangerous() 保留 shell=True，虽无调用者但是 public 安全隐患 | 替换为安全拒绝存根，返回错误 | 2026-03-26 | 第34轮审计 |
| HI-218 | `backend` | `security.py` | PIN 验证无频率限制，4位 PIN 可 10000 次穷举 | 5 次失败锁定 5 分钟 + 成功清除计数 | 2026-03-26 | 第34轮审计 |
| HI-219 | `backend` | `shared_memory.py` | Mem0 Cloud API add() 签名与本地不兼容，Cloud 模式记忆写入报错 | isinstance 分支: Cloud 传字符串, 本地传消息列表 | 2026-03-26 | 第34轮审计 |
| HI-220 | `backend` | `shared_memory.py` | search/semantic_search chat_id=None 时 user_id=None 跨用户记忆泄漏 | 默认 user_id="global" 兜底 | 2026-03-26 | 第34轮审计 |
| HI-221 | `backend` | `life_automation.py` | fire_due_reminders 并发重复触发 — SELECT+UPDATE 非原子 | 改为先 UPDATE 原子标记 fired，再 SELECT 已标记行 | 2026-03-26 | 第34轮审计 |
| HI-222 | `xianyu` | `order_notifier.py` | Telegram 订单通知只尝试一次，限流/超时即丢失 | 3 次指数退避重试 | 2026-03-26 | 第34轮审计 |
| HI-223 | `backend` | `life_automation.py` | evaluate_strategy_performance win_rate 单位假设可能错误 | 自动检测: >1 视为百分比需除 100 | 2026-03-26 | 第34轮审计 |
| HI-224 | `backend` | `life_automation.py` | get_expense_summary 最近5笔不受 days 参数限制 | SQL 添加 AND ts>? 时间筛选 | 2026-03-26 | 第34轮审计 |
| HI-225 | `backend` | `_db.py` + `life_automation.py` | post_engagement 无唯一约束，重复插入导致数据翻倍 | UNIQUE(draft_id, platform) + INSERT OR REPLACE | 2026-03-26 | 第34轮审计 |
| HI-226 | `deploy` | `deploy_vps.sh` | SSH 以 root 连接 + VPS IP 硬编码 | 改为 clawbot 用户 + 环境变量读取 | 2026-03-26 | 第34轮审计 |
| HI-228 | `deploy` | `deploy_client.py` + `auto_download.py` | 2 处 subprocess shell=True 命令注入 | 改为 shlex.split 列表调用 | 2026-03-26 | 第35轮审计 |
| HI-229 | `backend` | `api/server.py` | CORS allow_methods/headers=* 过于宽松 | 收窄为 GET/POST/PUT/DELETE + 3 个明确 header | 2026-03-26 | 第35轮审计 |
| HI-230 | `backend` | `github_trending.py` | aiohttp 无 sock_connect 超时 + 无重试 | sock_connect=10 + 3 次指数退避重试 | 2026-03-26 | 第35轮审计 |
| HI-231 | `backend` | `telegram_ux.py` | _delayed_flush create_task 无崩溃回调 | 添加 _flush_done 回调 | 2026-03-26 | 第35轮审计 |
| HI-232 | `backend` | `trading_system.py` | 2 处 except Exception: return 0.0/None 静默 | 改为 logger.debug 记录 | 2026-03-26 | 第35轮审计 |
| HI-233 | `backend` | `life_automation.py` | record_post_engagement 无输入验证，负数/非法平台可写入 | max(0) 校验 + 平台白名单 | 2026-03-26 | 第35轮审计 |
| HI-234 | `backend` | `life_automation.py` | _calc_next_occurrence 无最小间隔保护，"每1分钟"导致轰炸 | min 5 分钟钳位 | 2026-03-26 | 第35轮审计 |
| HI-235 | `backend` | `life_automation.py` | delete_last_expense 无 chat_id 隔离 | 新增 chat_id 可选参数 + SQL 条件 | 2026-03-26 | 第35轮审计 |
| HI-236 | `xianyu` | `xianyu_context.py` | get_pending_shipments 用 UTC 时间而 daily_stats 用 ET | 统一为 now_et() + timedelta | 2026-03-26 | 第35轮审计 |
| HI-237 | `infra` | `backup_databases.py` | 备份后无完整性验证 | PRAGMA integrity_check + 失败删除损坏备份 | 2026-03-26 | 第35轮审计 |
| HI-238 | `infra` | `monitoring.py` | /health 端点仅返回 {"status":"ok"} 无子系统状态 | 增加 uptime_seconds + components 字段 | 2026-03-26 | 第35轮审计 |
| HI-239 | `backend` | `news_fetcher.py` | asyncio.get_event_loop() 在 Python 3.12 已弃用 | 改为 get_running_loop() | 2026-03-26 | 第36轮审计 |
| HI-240 | `infra` | `observability.py` | 3 处 ImportError: pass 静默吞掉，可观测初始化失败无提示 | 改为 logger.info 记录缺失模块名 | 2026-03-26 | 第36轮审计 |
| HI-241 | `backend` | `life_automation.py` | get_engagement_summary 无互动率计算，缺核心社媒指标 | 新增 engagement_rate = (likes+comments+shares)/views*100 | 2026-03-26 | 第36轮审计 |
| HI-242 | `xianyu` | `xianyu_context.py` | 利润核算不扣佣金(闲鱼6%) | ALTER TABLE + commission_rate 字段 + 利润公式扣除 | 2026-03-26 | 第36轮审计 |
| HI-243 | `xianyu` | `xianyu_context.py` | notified 字段用魔术数字 0/1/2 | 新增 NOTIFY_NONE/ORDER/SHIPMENT 常量，4处替换 | 2026-03-26 | 第36轮审计 |
| HI-244 | `backend` | `cmd_basic_mixin.py` | onboarding 新闻获取失败暴露 Python 异常 str(e) | 改用 error_service_failed() | 2026-03-26 | 第36轮审计 |
| HI-245 | `backend` | `cmd_ibkr_mixin.py` | 3 处 IBKR 错误消息暴露 API 内部错误 | 统一改用 error_service_failed() | 2026-03-26 | 第36轮审计 |
| HI-246 | `backend` | `cmd_invest_mixin.py` | 2 处"降级"技术术语暴露给用户 | 改为"实盘暂不可用，已在模拟组合执行" | 2026-03-26 | 第36轮审计 |
| HI-247 | `backend` | `cmd_execution_mixin.py` | 未知子命令提示缺 emoji，与其他命令风格不一致 | 添加 ❓ 前缀 + 优化文案 | 2026-03-26 | 第36轮审计 |
| HI-248 | `frontend` | `Dashboard/index.tsx` | 状态/日志 catch 仅 console.warn，用户无感知 | 首次失败 toast.warning + useRef 防重复 | 2026-03-26 | 第36轮审计 |
| HI-249 | `frontend` | `Settings/index.tsx` | loading 时渲染空表单无骨架屏 | 提前返回加载动画组件 | 2026-03-26 | 第36轮审计 |
| HI-250 | `backend` | `agent_tools.py` | List, Optional import 未使用 | 删除未使用 import | 2026-03-26 | 第37轮审计 |
| HI-251 | `frontend` | `AIConfig/index.tsx` | 空 catch {} 吞掉 getProjectContext 错误 | 添加 console.debug 日志 | 2026-03-26 | 第37轮审计 |
| HI-252 | `frontend` | `Sidebar.tsx` | 固定 w-64 无响应式，小屏占比过大 | w-16 lg:w-64 + hidden lg:inline 文字隐藏 | 2026-03-26 | 第37轮审计 |
| HI-253 | `frontend` | `Dashboard/index.tsx` | grid-cols-1 直跳 xl:grid-cols-3，缺 lg 过渡 | 添加 lg:grid-cols-2 中间断点 | 2026-03-26 | 第37轮审计 |
| HI-254 | `backend` | 10个文件 | 20 处 `except Exception:` 无 `as e` 完全静默，异常信息丢失无法调试 | 全部改为 `except Exception as e:` + `logger.debug` 记录 | 2026-03-26 | 第38轮审计 |
| HI-255 | `docs` | `MODULE_REGISTRY.md` | 5 个安全关键模块 (code_tool/bash_tool/security/rpc/shared_memory) 未注册 | 补注册 5 个模块 + 新建 core 分组 | 2026-03-26 | 第39轮审计 |
| HI-256 | `docs` | `MODULE_REGISTRY.md` | 4 个模块描述过时 (wechat_bridge/feedback/xianyu_context/life_automation) | 描述追加安全/可靠性改进 | 2026-03-26 | 第39轮审计 |
| HI-257 | `backend` | `trading_system.py` | start_trading_system() 786 行单函数——项目最大技术债 | 拆为 5 个恢复函数 + _setup_scheduler + 33 行编排函数 | 2026-03-26 | 第40轮审计 |
| HI-258 | `backend` | `trading_system.py` | _setup_scheduler() 698 行——10个内联任务函数混在一起 | 10 个函数提取到模块级 + _setup_scheduler 缩为 48 行 | 2026-03-26 | 第41轮审计 |
| HI-259 | `backend` | `telegram_ux.py` | 循环导入: telegram_ux → bot.error_messages → bot.__init__ → cmd_basic → telegram_ux | error_messages 改为延迟导入 (函数内 import) | 2026-03-26 | 第41轮审计 |
| HI-260 | `backend` | `test_import_smoke.py` | 20个大型模块(300+行)无任何测试，导入链未验证 | 新增 20 个参数化导入烟雾测试 | 2026-03-26 | 第41轮审计 |
| HI-227 | `infra` | `monitoring.py` | Prometheus _histograms 渲染为 summary 类型，Grafana 查询异常 | 修正为 histogram | 2026-03-26 | 第34轮审计 |
| HI-205 | `deploy` | `kiro-gateway/config.py` | Gateway 默认绑定 0.0.0.0 暴露公网 | 默认改为 127.0.0.1 | 2026-03-26 | 第33轮审计 |
| HI-206 | `backend` | `security.py` | PIN 使用无盐 SHA-256，4位 PIN 可毫秒暴力破解 | PBKDF2 + 随机盐(100K轮) + chmod 600 + 向后兼容 | 2026-03-26 | 第33轮审计 |
| HI-207 | `backend` | `wechat_bridge.py` | contextToken 无 TTL 过期后首次发送必失败；无重试机制 | 30分钟 TTL 自动刷新 + 3次指数退避重试 + 401/403 清缓存 | 2026-03-26 | 第33轮审计 |
| HI-208 | `backend` | `notifications.py` | 微信桥接 except Exception: pass 完全静默 | 改为 logger.debug 记录异常 | 2026-03-26 | 第33轮审计 |
| HI-209 | `backend` | `scheduler.py` | 调度主循环 create_task 无崩溃回调 | 添加 _scheduler_done 回调 | 2026-03-26 | 第33轮审计 |
| HI-210 | `backend` | `quote_cache.py` | 报价刷新 create_task 无崩溃回调 | 添加 _quote_refresh_done 回调 | 2026-03-26 | 第33轮审计 |
| HI-211 | `backend` | `monitoring.py` | 自动恢复 create_task 无崩溃回调 | 添加 _recovery_done 回调 | 2026-03-26 | 第33轮审计 |
| HI-212 | `backend` | `execution/__init__.py` | triage_email 用废弃的 get_event_loop().run_until_complete() | 改为 async def + await | 2026-03-26 | 第33轮审计 |
| HI-213 | `backend` | `chinese_nlp_mixin.py` | dispatch_map 重复键 social_report + 缺失 draw/memory/settings 触发词 | 删除重复 + 新增 3 组中文触发词 | 2026-03-26 | 第33轮审计 |
| HI-214 | `backend` | `daily_brief.py` | 4 处 except Exception: pass 静默吞掉日报数据源异常 | 改为 logger.debug 记录 | 2026-03-26 | 第33轮审计 |
| HI-215 | `backend` | 6个文件 | 20+ 未使用 import (rpc.py/trading.py/cmd_collab/backtester/alpaca/backtest_reporter) | 删除全部未使用 import | 2026-03-26 | 第33轮审计 |
| HI-181 | `backend` | `code_tool.py` | Node.js execute_node() 无沙箱，可执行任意文件/网络/进程操作 | 添加沙箱前导代码禁用 12 个危险模块 + process.env/exit | 2026-03-26 | 第32轮审计 |
| HI-182 | `backend` | `api/rpc.py` | 14 处 `str(e)` 直接返回客户端，泄露内部路径和技术细节 | 新增 `_safe_error()` 脱敏函数 + 14 处替换 | 2026-03-26 | 第32轮审计 |
| HI-183 | `deploy` | `deploy_server.py` | 部署服务默认绑定 0.0.0.0，暴露公网 | 默认改为 127.0.0.1 | 2026-03-26 | 第32轮审计 |
| HI-184 | `backend` | `broker_bridge.py` | create_subprocess_shell 执行环境变量命令，可被注入 | 改为 create_subprocess_exec + shlex.split | 2026-03-26 | 第32轮审计 |
| HI-185 | `backend` | `chinese_nlp_mixin.py` | CRITICAL: 记账功能 NameError — action_data 变量名错误 + user/chat_id 未定义 | 修复变量名 + 提取 user/chat_id | 2026-03-26 | 第32轮审计 |
| HI-186 | `xianyu` | `xianyu_context.py` | SQLite 连接永不关闭 — _conn() 返回裸连接，每次调用泄漏连接 | @contextmanager + try/finally close | 2026-03-26 | 第32轮审计 |
| HI-187 | `deploy` | `license_manager.py` | 同 HI-186，SQLite 连接泄漏 | 同上，@contextmanager 模式 | 2026-03-26 | 第32轮审计 |
| HI-188 | `backend` | `auto_trader.py` | 交易主循环 create_task 无 done_callback，崩溃静默 | 添加 _main_loop_done 回调 + logger.critical | 2026-03-26 | 第32轮审计 |
| HI-189 | `backend` | `position_monitor.py` | 持仓监控循环无 done_callback，止损告警静默失效 | 添加 _monitor_done 回调 + logger.critical | 2026-03-26 | 第32轮审计 |
| HI-190 | `backend` | `feedback.py` | check_same_thread=False 无锁保护，多线程可损坏数据 | 添加 threading.Lock 保护所有 DB 操作 | 2026-03-26 | 第32轮审计 |
| HI-191 | `backend` | `monitoring.py` | _init_db 中 SQLite 连接异常可泄漏 | try/finally 包装 + finally close | 2026-03-26 | 第32轮审计 |
| HI-192 | `backend` | `message_mixin.py` | 3 处 fire-and-forget create_task 无异常回调 | 添加 _task_done 回调 + logger.debug | 2026-03-26 | 第32轮审计 |
| HI-193 | `backend` | `brain.py` | 多参数追问时所有参数被赋同一个 answer | 只赋值给第一个缺失参数，其余保留后续追问 | 2026-03-26 | 第32轮审计 |
| HI-194 | `xianyu` | `xianyu_context.py` | 利润核算不工作 — record_order 不接受 amount/cost | 新增 amount/cost 可选参数 + INSERT 同步 | 2026-03-26 | 第32轮审计 |
| HI-195 | `backend` | `life_automation.py` | add_expense 接受负数/零/极大值金额 | 添加 0.01~1M 范围校验 + 字段长度截断 | 2026-03-26 | 第32轮审计 |
| HI-196 | `backend` | `ocr_processors.py` | 高销量平均价格分母用全部条目数而非有价格的条目数 | 先筛 priced 子集，用 len(priced) 做分母 | 2026-03-26 | 第32轮审计 |
| HI-197 | `backend` | `cmd_analysis_mixin.py` | 3 处错误消息暴露 Python 异常技术细节 | 改用 error_service_failed() 统一模板 | 2026-03-26 | 第32轮审计 |
| HI-198 | `backend` | `cmd_collab_mixin.py` | 4 处错误消息暴露技术信息/英文异常 | 改用 error_service_failed() + 中文友好提示 | 2026-03-26 | 第32轮审计 |
| HI-199 | `frontend` | `cmd_basic_mixin.py` | 图片/二维码 caption 英文 Prompt/QR | 改为 描述/二维码 | 2026-03-26 | 第32轮审计 |
| HI-200 | `backend` | `cmd_execution_mixin.py` | 开发流程 OK/FAIL/stdout/stderr 英文 + 监控 ON/OFF | 改为 成功/失败/输出/错误/开启/关闭 | 2026-03-26 | 第32轮审计 |
| HI-201 | `backend` | `response_cards.py` | 按钮英文缩写 TA + 重复 cmd:cost 按钮 | 改为 技术分析 + 第二个改为 cmd:metrics | 2026-03-26 | 第32轮审计 |
| HI-202 | `backend` | `cmd_invest_mixin.py` | 自选股英文介词 [by xxx] | 改为 [来自 xxx] | 2026-03-26 | 第32轮审计 |
| HI-203 | `frontend` | `CommandPalette.tsx` | 导航项英文 Dashboard | 改为 概览 | 2026-03-26 | 第32轮审计 |
| HI-179 | `backend` | `proactive_engine.py` | Gate/Critic 用最强免费模型浪费 token | Gate+Critic 改用 g4f(最便宜) + max_tokens 100, 仅 Generate 用 qwen | 2026-03-26 | Token 优化 |
| HI-009 | `ai-pool` | `litellm_router.py` | 硅基付费Key未实名 | 启动时 validate_keys() 自动检测并 warning，/keyhealth 命令手动检查 | 2026-03-26 | 已有监控 |
| HI-010 | `ai-pool` | `config/.env` | NVIDIA NIM 信用额度制 | 同上，validate_keys() 自动检测 | 2026-03-26 | 已有监控 |
| HI-012 | `ai-pool` | `litellm_router.py` | GPT_API_Free 模型列表变动 | 同上，validate_keys() 自动检测 | 2026-03-26 | 已有监控 |
| HI-152 | `backend` | 16个模块 | 搬运代码未接入主流程 | 深度调研: 5已激活/6待配置/3待集成/1独立脚本/1技术债。monitoring_extras 接入 monitoring.py | 2026-03-26 | 模块调研 |
| HI-172 | `frontend` | `Memory/index.tsx` | 使用硬编码 Mock 数据 | 改为调用真实 API `/api/v1/memory/search` + 空状态友好提示 | 2026-03-26 | 前端接真 |
| HI-173 | `frontend` | `Social/Money/index.tsx` | handleAction 用 setTimeout 模拟 | 改为调用 `/api/v1/omega/process` POST + 错误反馈 | 2026-03-26 | 前端接真 |
| HI-177 | `backend` | `api/routers/` | 30/44 端点缺 response_model | omega(14)+social(14)+trading(3) 共 31 个端点添加 Dict[str,Any] | 2026-03-26 | API 规范 |
| HI-178 | `frontend` | `Service/` | Service 目录完全为空，无任何文件 | 删除空目录 | 2026-03-26 | 基础设施修复 |
| HI-174 | `docs` | `MODULE_REGISTRY.md` | 30 个实际模块未注册 + 1 个幽灵引用 | 新增 32 个模块条目(4,652行) + 删除 execution_hub 幽灵引用 | 2026-03-26 | 文档同步 |
| HI-175 | `docs` | `DEPENDENCY_MAP.md` | 13 包未登记 + 总数统计错误 | 新增 13 个包 + 总数 66→79 | 2026-03-26 | 文档同步 |
| HI-176 | `docs` | `PROJECT_MAP.md` | 10 文件行数过时/矛盾 + 幽灵引用 | 统一 10 个文件行数 + execution_hub/view 标记废弃 | 2026-03-26 | 文档同步 |
| HI-099 | `infra` | LaunchAgent 日志 | 日志无轮转无限增长 | newsyslog 配置已存在，覆盖 8 个服务(需 sudo 安装) | 2026-03-26 | 基础设施修复 |
| HI-146 | `backend` | `src/tools/bash_tool.py` | CRITICAL: shell=True + 黑名单模式安全不可靠，可被绕过执行任意命令 | shell=False + shlex.split + 白名单模式 (ALLOWED_COMMANDS frozenset) | 2026-03-25 | 安全加固 |
| HI-147 | `backend` | `src/tools/code_tool.py` | CRITICAL: 执行任意 Python/Node/Shell 代码无沙箱 | Python 沙箱 import hook + Shell 执行禁用 + 代码大小限制 10K + 临时文件清理 | 2026-03-25 | 安全加固 |
| HI-148 | `xianyu` | `xianyu_agent.py` | HIGH: Prompt 注入 — 用户消息拼入 system prompt | 对话历史隔离标记 + 防注入指令 | 2026-03-25 | 安全加固 |
| HI-149 | `backend` | `life_automation.py` | HIGH: osascript 注入 + URL scheme 未校验 | 正则白名单过滤 + urlparse scheme 校验 | 2026-03-25 | 安全加固 |
| HI-150 | `backend` | `api/auth.py` | HIGH: API Token 未配置时无认证 | 绑定非 localhost 时 logger.critical 警报 | 2026-03-25 | 安全加固 |
| HI-151 | `backend` | `message_mixin.py` | MEDIUM: discuss 摘要/评分未实现 | _fallback_summary_payload 实现 + _parse_workflow_ratings 支持数字/emoji | 2026-03-25 | 功能补全 |
| HI-170 | `deploy` | `docker-compose.yml` | MEDIUM: Dockerfile 不存在 | 创建多阶段 Dockerfile + .dockerignore (非root/最小镜像) | 2026-03-25 | 运维修复 |
| HI-153 | `backend` | `cmd_execution_mixin.py` | BLOCKER: SyntaxError 导致整个 Bot 启动失败 (error_service_failed 拼接缺加号) | 添加字符串连接符 `+` | 2026-03-25 | 第31轮全量审计 |
| HI-154 | `backend` | `evolution/engine.py` | BLOCKER: 语法错误 — `from src.utils import now_et` 插入 github_trending import 括号内 | 移到括号外作为独立语句 | 2026-03-25 | 第31轮全量审计 |
| HI-155 | `backend` | `monitoring.py` | BLOCKER: CostAnalyzer 3个方法 (analyze_by_user/feature/cleanup) SQLite连接不在 try/finally | 改为 `with sqlite3.connect(timeout=10) as conn:` | 2026-03-25 | 第31轮全量审计 |
| HI-156 | `backend` | `cmd_basic_mixin.py` | HIGH: settings callback 越权 — 任何用户可伪造 user_id 修改他人设置 | 添加 `from_user.id == user_id` 校验 | 2026-03-25 | 第31轮全量审计 |
| HI-157 | `backend` | `api/routers/omega.py` | HIGH: 20处 API 端点 `str(e)` 泄露内部路径和技术细节 | 新增 `_safe_error()` 脱敏函数替代 | 2026-03-25 | 第31轮全量审计 |
| HI-158 | `backend` | `proactive_engine.py` | MEDIUM: 10处 `except Exception: pass` 完全静默，排障困难 | 改为 `logger.debug(f"[Proactive] {上下文}: {e}")` | 2026-03-25 | 第31轮全量审计 |
| HI-159 | `backend` | `media_crawler_bridge.py` | MEDIUM: httpx.AsyncClient 无 close() 方法，TCP 连接泄漏 | 添加 `async close()` 方法 | 2026-03-25 | 第31轮全量审计 |
| HI-160 | `xianyu` | `goofish_monitor.py` | MEDIUM: httpx.AsyncClient 无 close() 方法，TCP 连接泄漏 | 添加 `async close()` 方法 | 2026-03-25 | 第31轮全量审计 |
| HI-161 | `backend` | `brain.py` | LOW: 3个未使用 import (json, Callable, EventBus) | 删除 | 2026-03-25 | 第31轮全量审计 |
| HI-162 | `backend` | `message_mixin.py` | LOW: 9个未使用 import (base64, CLAUDE_BASE/KEY, chat_router等) | 删除 | 2026-03-25 | 第31轮全量审计 |
| HI-163 | `backend` | `auto_trader.py` | LOW: 未使用 import `dataclass` | 删除 | 2026-03-25 | 第31轮全量审计 |
| HI-164 | `backend` | `risk_manager.py` | LOW: 未使用 import `math` | 删除 | 2026-03-25 | 第31轮全量审计 |
| HI-165 | `deploy` | `deploy_vps.sh` | CRITICAL: rsync 未排除 .venv312/.git/api_keys.json，systemd ProtectHome冲突，pip全局安装 | 全面重写: +9 排除项, ProtectHome=read-only, venv隔离, CPUQuota, -u unbuffered, EnvironmentFile | 2026-03-25 | 第31轮全量审计 |
| HI-166 | `deploy` | `docker-compose.yml` | HIGH: 端口暴露 0.0.0.0 + Redis 镜像未锁定 + 主服务无资源限制 + healthcheck 依赖 httpx | 端口绑定 127.0.0.1, Redis 7.2, 添加资源限制 2G/1.5CPU, healthcheck 改 urllib | 2026-03-25 | 第31轮全量审计 |
| HI-167 | `frontend` | `Evolution/index.tsx` | UX: 整个页面全英文 UI (19处标题/按钮/标签/提示) | 全部替换为中文 | 2026-03-25 | 第31轮全量审计 |
| HI-168 | `frontend` | `Plugins/index.tsx` | UX: 9处英文描述/状态标签 | 全部替换为中文 | 2026-03-25 | 第31轮全量审计 |
| HI-169 | `frontend` | `Dashboard/Evolution/Settings` | UX: 6处操作类 catch 仅 console.error，用户无反馈 | 添加 toast.error 通知 | 2026-03-25 | 第31轮全量审计 |
| HI-144 | `backend` | `_db.py`, `life_automation.py`, `chinese_nlp_mixin.py` | FUNC: 记账功能完全缺失—LIFE TaskType核心场景 | expenses表+3个函数+4组中文触发词+分发 | 2026-03-25 | 功能补全 |
| HI-145 | `frontend` | `AIConfig/index.tsx` | P4: 1157行巨石组件 | 拆分为types+ProviderDialog+ProviderCard+index 4个文件 | 2026-03-25 | 功能补全 |
| HI-140 | `backend` | 7个cmd_*.py | UX-CRITICAL: 仅4/68命令有typing指示器，用户发命令后死寂2-30秒 | 59个命令添加@with_typing，覆盖率5.9%→92.6% | 2026-03-25 | 交互体验大修 |
| HI-141 | `backend` | `worker_bridge.py` | P3: subprocess.run+time.sleep阻塞事件循环最长5分钟 | 新增run_social_worker_async()异步版本 | 2026-03-25 | 交互体验大修 |
| HI-142 | `backend` | `error_messages.py`, `cmd_invest_mixin.py`, `cmd_execution_mixin.py` | UX: 7处硬编码错误消息暴露技术细节/stderr | 新增error_service_failed模板+替换 | 2026-03-25 | 交互体验大修 |
| HI-133 | `backend` | `response_cards.py` | UX: SystemStatusCard 2个死按钮指向不存在的命令 | 替换为实际存在的 cmd:cost + cmd:settings | 2026-03-25 | P6/P8审计修复 |
| HI-134 | `backend` | `free_apis.py`, `chinese_nlp_mixin.py` | FUNC: 快递查询 API 存在但无用户入口 | 新增 query_express() + 中文触发词"查快递" | 2026-03-25 | P6/P8审计修复 |
| HI-135 | `xianyu` | `daily_brief.py` | FUNC: 闲鱼数据未整合进主日报 | 新增 Section 11 闲鱼运营数据段 | 2026-03-25 | P6/P8审计修复 |
| HI-136 | `frontend` | `Channels/index.tsx`, `AIConfig/index.tsx` | UX: 7处 alert() 阻塞用户体验 | 替换为 toast (sonner) | 2026-03-25 | P6/P8审计修复 |
| HI-137 | `frontend` | 6个组件 | UX: 14处英文状态标签 (Service Status/Online/Running等) | 全部中文化 | 2026-03-25 | P6/P8审计修复 |
| HI-138 | `frontend` | `Dashboard/index.tsx`, `SystemInfo.tsx` | BUG: 3处 catch{} 静默吞掉错误 | 添加 console.warn | 2026-03-25 | P6/P8审计修复 |
| HI-139 | `docs` | `PROJECT_MAP.md` | DOC: 4个幽灵占位目录误导 + 微信能力描述不准确 | 标记废弃+修正微信描述 | 2026-03-25 | P6/P8审计修复 |
| HI-111 | `trading` | `risk_manager.py` | CRITICAL: check_trade 不验证 entry_price/quantity>0，零价格导致除零，负数量绕过风控 | 添加参数合法性前置检查 | 2026-03-25 | 全面审计37项修复 |
| HI-112 | `trading` | `risk_manager.py` | CRITICAL: record_trade_result 日盈亏累加无锁，并发交易可绕过日亏损限额 | 添加 threading.Lock 保护 | 2026-03-25 | 全面审计37项修复 |
| HI-113 | `trading` | `broker_bridge.py` | HIGH: _place_order 不验证 quantity>0 + 预算追踪无锁 | 添加 quantity 前置验证 | 2026-03-25 | 全面审计37项修复 |
| HI-114 | `trading` | `auto_trader.py` | HIGH: SELL 订单完全绕过风控审核 | 风控检查扩展覆盖 BUY+SELL | 2026-03-25 | 全面审计37项修复 |
| HI-115 | `trading` | `auto_trader.py` | MEDIUM: parse_trade_proposal 可产出负数量 | max(0, ...) 拦截 | 2026-03-25 | 全面审计37项修复 |
| HI-116 | `backend` | `cmd_execution_mixin.py` | HIGH: 4 个命令别名(cmd_hot等)缺少 @requires_auth | 添加装饰器 | 2026-03-25 | 全面审计37项修复 |
| HI-117 | `backend` | `image_tool.py` | CRITICAL: httpx.AsyncClient 无 timeout，下载可永久阻塞 | 添加 timeout=30 | 2026-03-25 | 全面审计37项修复 |
| HI-118 | `backend` | `real_trending.py` | HIGH: httpx 无 timeout，热搜抓取可挂起 | 添加 timeout=20 | 2026-03-25 | 全面审计37项修复 |
| HI-119 | `backend` | `monitoring.py` | HIGH: CostAnalyzer 6处 SQLite 连接未用 with 语句，异常时泄漏 | 改为 with 上下文管理器 | 2026-03-25 | 全面审计37项修复 |
| HI-120 | `backend` | `_db.py`, `xianyu_context.py`, `feedback.py` | MEDIUM: 3 个 SQLite 数据库无 WAL 模式和 timeout | 添加 WAL + timeout=10 | 2026-03-25 | 全面审计37项修复 |
| HI-121 | `xianyu` | `xianyu_live.py` | HIGH: 自动接受无价格上限，误提取可导致错误成交 | 添加 <= floor * 10 合理范围 | 2026-03-25 | 全面审计37项修复 |
| HI-122 | `xianyu` | `xianyu_live.py` | HIGH: 4 个后台任务无 done_callback，崩溃不被发现 | 添加异常日志回调 | 2026-03-25 | 全面审计37项修复 |
| HI-123 | `backend` | `life_automation.py` | HIGH: cancel_reminder 重复定义，安全版被覆盖 | 删除第二个不安全版本 | 2026-03-25 | 全面审计37项修复 |
| HI-124 | `backend` | `life_automation.py` | MEDIUM: dateparser naive vs aware datetime 比较，自然语言时间解析退化 | 启用时区感知 + America/New_York | 2026-03-25 | 全面审计37项修复 |
| HI-125 | `backend` | `message_mixin.py` | MEDIUM: 3 处 except pass 静默吞掉异常 | 改为 logger.debug | 2026-03-25 | 全面审计37项修复 |
| HI-126 | `backend` | `proactive_engine.py`, `self_heal.py` | MEDIUM: 缓存无限增长 — _sent_log/_solution_cache | 添加定期清理 + maxsize | 2026-03-25 | 全面审计37项修复 |
| HI-127 | `infra` | `log_config.py` | MEDIUM: console diagnose=True 泄露局部变量 | 改为 False | 2026-03-25 | 全面审计37项修复 |
| HI-128 | `deploy` | `license_manager.py` | MEDIUM: License Key 完整记录到日志 | 脱敏为首尾各 4 字符 | 2026-03-25 | 全面审计37项修复 |
| HI-129 | `infra` | `backup_databases.py` | MEDIUM: 时区比较不一致可能导致清理逻辑报错 | 统一为 UTC aware | 2026-03-25 | 全面审计37项修复 |
| HI-130 | `deploy` | `kiro-gateway/docker-compose.yml` | HIGH: 默认密码硬编码 | 改为必填环境变量 | 2026-03-25 | 全面审计37项修复 |
| HI-131 | `deploy` | `docker-compose.yml` | HIGH: Redis 端口暴露+无资源限制 | expose + maxmemory + deploy.resources | 2026-03-25 | 全面审计37项修复 |
| HI-132 | `docs` | `DEPENDENCY_MAP.md` | MEDIUM: Python 版本文档过时 (写 3.9 实际用 3.12) | 更新为 3.12 | 2026-03-25 | 全面审计37项修复 |
| HI-110 | `backend` | `life_automation.py`, `scheduler.py`, `_db.py` | BUG: 提醒写入 SQLite 后无代码检查和触发，用户被"无声放鸽子" | `fire_due_reminders()` 每60秒检查到期提醒 + `_calc_next_occurrence()` 支持重复规则 + `cancel_reminder()` + DB 新增 `recurrence_rule`/`user_chat_id` 列 | 2026-03-25 | 提醒触发机制修复+重复提醒 |
| HI-006 | `backend` | `src/execution_hub.py` | 巨石文件 2,793 行 143 方法 — 全部通过 legacy 桥接间接使用 | 全部 143 方法迁移到 `src/execution/` 模块化包 (6 个新模块)，facade v3.0 不再加载 legacy 文件，`__getattr__` 改为 ERROR 级别 | 2026-03-24 | execution_hub 巨石拆分 |
| HI-008 | `backend` | `src/execution_hub.py` | 反编译来源 — 变量名不准确，通过桥接间接使用 | 所有反编译方法已重写为干净的模块函数，legacy 文件标记为 FULLY DEPRECATED 仅保留参考 | 2026-03-24 | execution_hub 巨石拆分 |
| HI-105 | `frontend` | `src-tauri/capabilities/default.json` | HIGH: Tauri shell 权限过宽 — `shell:allow-execute` + `shell:allow-spawn` 授予前端任意 shell 访问 | 替换为 `shell:allow-open-url`，Rust 侧 `std::process::Command` 不需要 webview shell 权限 | 2026-03-24 | Tauri安全+Python内存泄漏修复 |
| HI-106 | `frontend` | `src-tauri/tauri.conf.json` | MEDIUM: CSP 被禁用 (`csp: null`) — 无内容安全策略，XSS 攻击面暴露 | 设置严格 CSP: `default-src 'self'` + 限定 connect-src/script-src/style-src/img-src | 2026-03-24 | Tauri安全+Python内存泄漏修复 |
| HI-107 | `backend` | `src/chat_router.py`, `src/core/brain.py` | MEDIUM: `_discuss_sessions`/`_service_workflows`/`_pending_callbacks` 无清理，内存无界增长 | 添加 `cleanup_stale_sessions()` + `cleanup_pending_callbacks()` TTL 清理，接入 multi_main.py 60s 周期定时器 | 2026-03-24 | Tauri安全+Python内存泄漏修复 |
| HI-108 | `backend` | `src/bot/globals.py` | LOW: `_cleanup_pending_trades()` 引用 `datetime.fromisoformat()` 但未导入 `datetime` | 添加 `from datetime import datetime` | 2026-03-24 | Tauri安全+Python内存泄漏修复 |
| HI-109 | `docs` | `config/omega.yaml` | MEDIUM: `routing.task_routing`/`social.optimal_times`/`life.*` 定义但无代码消费 | 添加 `[PLANNED - not yet consumed by code]` 注释标注，保留配置供未来使用 | 2026-03-24 | Tauri安全+Python内存泄漏修复 |
| HI-103 | `infra` | `scripts/backup_databases.py`, `src/execution/scheduler.py` | 无数据库备份机制 — 9 个 SQLite 数据库无任何备份，硬件故障将导致全部数据丢失 | 新增 backup_databases.py (SQLite online backup API) + scheduler 04:00 ET 自动触发 + 7日/4周保留策略 | 2026-03-24 | 数据库备份+灾难恢复 |
| HI-104 | `deploy` | `scripts/deploy_vps.sh` | rsync 部署覆盖 VPS 数据库 — 本地 rsync 无 DB 排除，部署会用本地空/开发数据库覆盖生产数据 | 添加 --exclude 'data/*.db' + WAL/SHM + backups/ + qdrant_data/ + llm_cache/ | 2026-03-24 | 数据库备份+灾难恢复 |
| HI-100 | `backend` | `src/bot/message_mixin.py`, `src/bot/api_mixin.py` | 消息流3个间隙: 频率限制静默丢弃+8个空方法体+quality_gate丢失拒绝原因 | (a) rate_limiter 拒绝时回复 ⏳ 提示 (b) 8个空pass方法添加最小实现 (c) quality_gate 拒绝返回原因 | 2026-03-24 | HI-100/101/102 修复 |
| HI-101 | `backend` | `src/core/response_cards.py`, `src/bot/cmd_basic_mixin.py`, `src/bot/multi_bot.py` | ClarificationCard callback_data 格式不匹配任何注册 handler，按钮静默无响应 | 新增 handle_clarification_callback + CallbackQueryHandler pattern `^\d+:.+:.+$` 匹配追问按钮 | 2026-03-24 | HI-100/101/102 修复 |
| HI-102 | `docs` | `apps/openclaw/TELEGRAM_COMMANDS.md` | 6 个废弃命令 (/profit /alpha /recover /heal /channel /playbook) 映射不存在的 skills | 删除 6 个废弃命令条目及其使用示例 | 2026-03-24 | HI-100/101/102 修复 |
| HI-088 | `deploy` | `scripts/deploy_vps.sh` | HIGH: systemd 以 root 运行，无安全指令 | 切换为 clawbot 用户 + NoNewPrivileges/ProtectSystem/ProtectHome/PrivateTmp/MemoryMax 加固 | 2026-03-24 | 4项部署安全/数据稳定性修复 |
| HI-089 | `deploy` | `scripts/deploy_vps.sh` | HIGH: rsync 同步含 config/.env，API Keys 泄露到 VPS 环境变量 | rsync --exclude 'config/.env' | 2026-03-24 | 4项部署安全/数据稳定性修复 |
| HI-090 | `backend` | `src/data_providers.py` | HIGH: yfinance 每次请求均发起网络调用，无缓存无过期检测 | 60s TTL 内存缓存 + _stale_warning 交易日过期检测 | 2026-03-24 | 4项部署安全/数据稳定性修复 |
| HI-091 | `backend` | `scheduler.py`, `trading_journal.py`, `feedback.py` | HIGH: SQLite 数据库无清理机制，unbounded growth | 三模块 cleanup() 方法 + scheduler 03:00 ET 自动触发 | 2026-03-24 | 4项部署安全/数据稳定性修复 |
| HI-067 | `xianyu` | `src/xianyu/xianyu_live.py` | HIGH: 底价绕过 — `_extract_price()` 失败时 AI 不知底价，可能同意低于底价的报价 | 在 AI 调用前注入底价到 item_desc 上下文 | 2026-03-24 | 6项安全/稳定性修复 |
| HI-068 | `xianyu` | `src/xianyu/xianyu_live.py` | HIGH: 无消息速率限制 — 买家可发无限消息触发无限 LLM 调用 | 添加 per-chat 速率限制 (10 msgs/min, 可配置) | 2026-03-24 | 6项安全/稳定性修复 |
| HI-069 | `xianyu` | `src/xianyu/xianyu_agent.py` | MEDIUM: BaseAgent.agenerate() 定义两次，首次为死代码 | 删除死代码首次定义 | 2026-03-24 | 6项安全/稳定性修复 |
| HI-070 | `backend` | `src/shared_memory.py` | HIGH: Mem0 多租户隔离缺失 — 所有用户共享 agent_id="clawbot"，跨用户记忆泄露 | add/search 调用添加 user_id 参数，按用户隔离 | 2026-03-24 | 6项安全/稳定性修复 |
| HI-071 | `ai-pool` | `src/litellm_router.py` | HIGH: 错误日志可能泄露 API Key 和内网 URL | 新增 _scrub_secrets() 脱敏函数，应用于所有错误日志 | 2026-03-24 | 6项安全/稳定性修复 |
| HI-072 | `ai-pool` | `src/litellm_router.py` | MEDIUM: validate_keys() 报告死 key 但不禁用，死 key 持续被重试 | auth_error key 自动设置 disabled=True | 2026-03-24 | 6项安全/稳定性修复 |
| HI-063 | `xianyu` | `src/xianyu/xianyu_admin.py` | CRITICAL: 管理面板绑定 0.0.0.0 + CORS wildcard + 无认证 + 路径遍历 | 绑定 127.0.0.1 + CORS 白名单 + prompt 名称正则校验 | 2026-03-24 | 安全审计修复 |
| HI-064 | `backend` | `src/api/routers/omega.py` | HIGH: /omega/tools/jina-read SSRF — 无 URL 校验可请求内网 | URL scheme 白名单 + 内网地址黑名单 | 2026-03-24 | 安全审计修复 |
| HI-065 | `backend` | `requirements.txt` | HIGH: flask/aiohttp 缺失 + fpdf2 精确锁版本 + litellm/crewai/browser-use 无上界 | 添加缺失依赖 + 宽松化 fpdf2 + 3 个包添加上界 | 2026-03-24 | 安全审计修复 |
| HI-066 | `backend` | `omega.py`, `social.py` | MEDIUM: API 参数无边界校验 (limit/count/days/message) | 添加 Query(ge/le) + max_length 约束 | 2026-03-24 | 安全审计修复 |
| HI-050 | `trading` | `cmd_invest_mixin.py` | `/sell` 完全跳过风控检查，可绕过熔断/冷却 | 添加 rm.check_cooldown() + 持仓校验 | 2026-03-24 | 交易系统11项安全修复 |
| HI-060 | `trading` | `src/broker_bridge.py` | IBKR `total_spent` 纯内存变量，重启后归零，可重复花费整日预算 | 持久化到 `data/broker_budget_state.json`，启动时按日期恢复 | 2026-03-24 | 资金路径3项修复 |
| HI-061 | `trading` | `src/alpaca_bridge.py` | `_place_order()` 提交后立即返回 "submitted"，无实际成交价/数量 | 添加30秒轮询循环等待 filled/rejected 状态 | 2026-03-24 | 资金路径3项修复 |
| HI-062 | `trading` | `src/auto_trader.py` | `execute_proposal()` 不处理部分成交，journal/monitor 记录请求数量而非实际成交数量 | 从 order_result.filled_qty 提取实际成交量，用于 journal 和 monitor | 2026-03-24 | 资金路径3项修复 |
| HI-092 | `backend` | `src/log_config.py` | CRITICAL: loguru diagnose=True 在文件 sink 中泄露本地变量值 (可含 API Key/token) | 文件 sink diagnose=False，仅 console sink 保留 diagnose=True | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-093 | `backend` | `src/bot/globals.py` | HIGH: API Key 前缀日志暴露 20 字符，足以暴力破解后缀 | key[:20] → key[:8] | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-094 | `social` | `src/social_scheduler.py` | HIGH: job_night_publish 无发布状态锁，cron+手动重叠导致重复发布 | 发布前标记 publishing 并持久化，成功→published，异常→failed | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-095 | `trading` | `src/auto_trader.py` | HIGH: _safe_notify P0 通知 (成交/止损) 零重试，Telegram 短暂不可用导致永久丢失 | P0 通知 3 次重试 + 指数退避 | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-096 | `backend` | `multi_main.py` | HIGH: 关闭时 NotificationBatcher 未 flush，待发通知丢失 | 关闭序列开头添加 await _notify_batcher.flush() | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-097 | `backend` | `multi_main.py` | MEDIUM: 6 处 EventBus except Exception: pass 静默吞掉交易/风控事件失败 | 替换为 logger.debug 记录异常 | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-098 | `backend` | `multi_main.py` | MEDIUM: 全部 7 Bot 启动失败时系统静默运行，无任何告警 | 添加 logger.critical 零 Bot 检测 | 2026-03-24 | 日志/社交/通知7项修复 |
| HI-051 | `trading` | `cmd_invest_mixin.py` | 负数/零数量未校验，可下达无效订单 | buy/sell 路径均添加 quantity<=0 拦截 | 2026-03-24 | 交易系统11项安全修复 |
| HI-052 | `trading` | `cmd_invest_mixin.py` | 无重复下单保护，快速双击可能产生双倍订单 | 30秒 per-user:symbol 冷却防重 | 2026-03-24 | 交易系统11项安全修复 |
| HI-053 | `trading` | `message_mixin.py` | itrade fallback 调用 ibkr.place_order() 不存在 | 替换为 ibkr.buy()/ibkr.sell() | 2026-03-24 | 交易系统11项安全修复 |
| HI-054 | `trading` | `cmd_invest_mixin.py` | IBKR 零成交时仍写入幽灵持仓 | fill_qty<=0 时跳过 portfolio 写入 | 2026-03-24 | 交易系统11项安全修复 |
| HI-055 | `trading` | `cmd_invest_mixin.py` | rm=None 时所有风控检查被跳过 | 实盘(IBKR连接)场景下 rm=None 拒绝交易 | 2026-03-24 | 交易系统11项安全修复 |
| HI-056 | `trading` | `position_monitor.py` | 监控循环异常后不重启 | 添加 CancelledError 处理，异常后继续循环 | 2026-03-24 | 交易系统11项安全修复 |
| HI-057 | `trading` | `risk_manager.py` | calc_safe_quantity() 错误返回缺少 shares 键 | 添加 "shares": 0 到所有错误返回 | 2026-03-24 | 交易系统11项安全修复 |
| HI-058 | `trading` | `risk_manager.py` | reset_daily() 未重置分层状态 | 同步重置 _current_tier=0, _position_scale=1.0 | 2026-03-24 | 交易系统11项安全修复 |
| HI-059 | `trading` | `invest_tools.py` | Portfolio SQLite 无 WAL 模式和超时 | 添加 timeout=10 + PRAGMA journal_mode=WAL | 2026-03-24 | 交易系统11项安全修复 |
| HI-015 | `docs` | `docs/` | `apps/openclaw/AGENTS.md` 和 `packages/clawbot/docs/agents.md` 命名冲突 | 调查确认非冲突: 后者是部署 artifact，被 `web_installer.py:69` 和 `package.sh:24` 硬引用，用途不同 | 2026-03-24 | TS any 清理 |
| HI-038 | `trading` | `config/omega.yaml`, `src/risk_manager.py` | omega.yaml risk_rules 与 risk_manager.py RiskConfig 数值不一致: max_position 20%↔30%, daily_loss 3%↔5%($100), max_sector 35%↔50%, drawdown 8%↔10% | 统一以 risk_manager.py 为真值，omega.yaml/brain.py/bot_profiles.py/cmd_collab_mixin.py 全部对齐 | 2026-03-24 | 风控参数统一 |
| HI-039 | `backend` | 全局 | 人格称呼三套并存 (Boss/严总/老板)，IDENTITY.md 与 AGENTS.md/USER.md 矛盾 | 全局统一为「严总」: 31 个文件 ~75 处替换 (IDENTITY.md/30+ skills/cron/Python/Tauri) | 2026-03-24 | 架构清爽化 |
| HI-040 | `backend` | 7 个文件 | 42+ 处内联系统提示词散落在 brain.py/intent_parser.py/team.py/pydantic_agents.py/cmd_collab_mixin.py | 创建 `config/prompts.py` 集中定义，5 个消费文件改为 import 引用 | 2026-03-24 | 架构清爽化 |
| HI-041 | `backend` | 10+ 文件 | 僵尸文件/包: shared_memory_v3_backup/migrate_memory_to_mem0/updater/memory_layer/config_schema/agent_skills/routing/ | 删除 8 个文件 + 2 个目录，共 3,091 行 | 2026-03-24 | 架构清爽化 |
| HI-042 | `backend` | 7 个 mixin 文件 | 76 处重复 `if not self._is_authorized(...)` 权限检查 | 创建 `@requires_auth` 装饰器，70 处替换完成 | 2026-03-24 | 架构清爽化 |
| HI-043 | `backend` | 6 个文件 | 错误消息 4 种风格不统一 (抱歉/⚠️/操作失败/系统繁忙) | 创建 `error_messages.py` 统一模板，15 处替换 | 2026-03-24 | 架构清爽化 |
| HI-044 | `backend` | `risk_manager.py` | `remaining_daily_budget` 与 LLM cost `daily_budget` 命名冲突 | 重命名为 `remaining_daily_loss_budget` | 2026-03-24 | 架构清爽化 |
| HI-045 | `backend` | `globals.py`, `telegram_gateway.py` | Admin 用户 ID 3 种环境变量名 (ALLOWED_USER_IDS/OMEGA_ADMIN_USER_IDS/admin_user_ids) | 统一为 `ALLOWED_USER_IDS`，gateway 向后兼容读取 | 2026-03-24 | 架构清爽化 |
| HI-046 | `backend` | `cmd_basic_mixin.py` | Help 键盘定义在 2 处完全重复 | 提取为 `_build_help_main_keyboard()` 函数 | 2026-03-24 | 架构清爽化 |
| HI-017 | `frontend` | `lib/tauri.ts` | 35+ 个 `invokeWithLog<any>` 调用缺少具体类型 | 实测 tauri.ts 零 any (全部已使用具体类型)，原记录数据过时 | 2026-03-24 | Phase 6 |
| HI-026 | `frontend` | 多组件 | 22→6 处 `: any` 类型注解 | 全部修复: Connection/React.MouseEvent/LucideIcon/Record<string,unknown>[] | 2026-03-24 | Phase 6 |
| HI-007 | `backend` | `src/bot/message_mixin.py` | 反编译来源 (Decompyle++ 标记) — 25 个非 raw-string regex + 变量名 + dead code | 移除 Decompyle++ header，修复 25 regex 为 raw string，重命名变量，清理 dead code | 2026-03-24 | Phase 5 |
| HI-013 | `ai-pool` | `src/litellm_router.py` | Gemini 2.0 系模型已被 Google 废弃 — 已从 deployment 和 MODEL_RANKING 中移除 | 从 deployment 和排名中删除 gemini-2.0-flash | 2026-03-23 | Phase 1 |
| HI-011 | `backend` | `src/bot/message_mixin.py` | 流式输出群聊频率过高触发 Telegram flood 限制 | 5层修复: 时间门控(3s群/1s私) + 编辑次数上限(15/30) + 指数退避 + cutoff提升(80-300) + 生产端节流(300ms) | 2026-03-23 | Phase 1 |
| HI-025 | `backend` | 30+ 文件 | 117 处 `datetime.now()` 裸调用残留 — 交易/调度核心路径已修复，日志/元数据路径约 100 处待清理 | 全局清扫 `datetime.now()` 替换为从 `src.utils` 引入的 `now_et()` | 2026-03-23 | 全量审计 |
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
| HI-047 | `backend` | `src/execution/__init__.py` | ExecutionHub facade 4 个方法签名与调用方不匹配 (build_social_plan/research_social_topic/scan_bounties/run_bounty_hunter) — 运行时 TypeError 崩溃 | 转为 legacy delegate 透传 *args/**kwargs | 2026-03-24 | facade签名修复 |
| HI-048 | `backend` | `multi_main.py`, `src/core/brain.py` | 11 处 fire-and-forget `asyncio.create_task` 无 done callback — 后台任务异常被静默吞掉 | 添加 `add_done_callback` + `_task_done_cb` 辅助函数 | 2026-03-24 | 并发安全加固 |
| HI-049 | `backend` | `src/feedback.py` | FeedbackStore SQLite 连接无 close() 方法 — 资源泄漏 | 添加 `close()` 方法 | 2026-03-24 | 并发安全加固 |
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
| `backend` | ~~两个巨石反编译文件占总代码量 ~10%~~ | 项目早期从 `.pyc` 逆向恢复 | **已解决**: execution_hub.py 已删除(2795行); message_mixin.py 拆分-40%(提取OCRMixin+ChineseNLPMixin) + 15处反编译残留清理 | HI-006, HI-007, HI-008 |
| `ai-pool` | 多个第三方 API 限制频繁变动 | 依赖免费/试用层 API | 建立定期巡检机制，自动检测 key 余额和模型可用性 | HI-009, HI-010, HI-012, HI-013 |
| `backend` | ~~Telegram 流式输出 flood 限制~~ | 群聊编辑频率过高 | **已解决**: 时间门控+编辑上限+指数退避+cutoff提升+生产端节流 | ~~HI-011~~ |
| `backend` | ~~117 处 `datetime.now()` 裸调用~~ | 早期代码未统一时区策略 | **已解决**: 生产代码 9 处裸调用全部修复为 `datetime.now(timezone.utc)`, 仅剩测试代码 19 处 | HI-025 |
| `backend` | ~~人格称呼/提示词/配置散落多处~~ | 早期无统一治理机制 | **已解决**: `config/prompts.py` SSOT + SOUL_CORE 统一 + env var 收敛 | HI-039~046 |
| `backend` | src/ 根目录 61 个 .py 文件平铺 | 早期快速开发无分包 | 风险过高暂缓: utils.py 被 61 文件 import, 需先补测试覆盖再分批迁移 | — |
| `backend` | 🟡 HI-360: 14个文件超过1000行(4个超过1500行)，top候选: brain.py/message_mixin.py/auto_trader.py/execution_life_automation.py | 早期快速开发+功能堆积 | 按 God Object 拆分模式逐文件拆解，优先拆 1500+ 行文件 | — |

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
| 🔴 阻塞 | 0 | 16 | 16 |
| 🟠 重要 | 4 | 88 | 92 |
| 🟡 一般 | 3 | 102 | 105 |
| 🔵 低优先 | 1 | 31 | 32 |
| **合计** | **8** | **237** | **245** |

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
