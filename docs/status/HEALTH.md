# HEALTH.md — 系统健康仪表盘

> 最后更新: 2026-04-19 (R3+R4 审计完成: R3 3项修复+3技术债 / R4 0修复+8技术债)
> Bug 生命周期: 发现 → 记录到「活跃问题」→ 修复 → 移至「已解决」→ 运维AI从模式中识别「技术债务」
> 严重度: 🔴 阻塞 | 🟠 重要 | 🟡 一般 | 🔵 低优先

---

## 功能优先级矩阵 (CEO 拍板, 2026-03-23)

> 得分公式: 痛点烈度×2 - 技术成本。🚀立即 = 本周启动 | ⏳待定 = 下个迭代

### Phase 1 — 本周必须做

| # | 功能 | 痛点(1-5) | 成本(1-5) | 得分 | 决策 | 关联 HI |
|---|-----|----------|----------|------|------|---------|
| 1 | sanitize_input 安全实现 | 5 | 2 | 8 | ✅ 完成 | HI-037 |
| 2 | ~~Telegram flood 根治~~ | 4 | 3 | 5 | ✅ 完成 | HI-011 |
| 3 | ~~execution_hub.py 引用切换完成~~ | 4 | 4 | 4 | ✅ 完成 | HI-006 |

> **HI-037 备注**: ✅ 已在 `message_mixin.py:214` 接入消息处理管道 (P0安全审计修复, 2026-03-30)。`sanitize_input()` 方法定义在 `security.py:281`。

### Phase 2 — 核心价值兑现

| # | 功能 | 痛点(1-5) | 成本(1-5) | 得分 | 决策 | 关联 HI |
|---|-----|----------|----------|------|------|---------|
| 4 | ~~IBKR 实盘接入~~ | 5 | 3 | 7 | ✅ 完成 | — |
| 5 | ~~投资决策→回测→执行闭环~~ | 5 | 2 | 8 | ✅ 完成 | — |
| 6 | ~~反编译文件重写 (message_mixin 优先)~~ | 4 | 5 | 3 | ⏸ 降级 | HI-007/008 |

> **#6 备注**: 经 2026-04-16 侦察确认，`message_mixin.py` **并非反编译文件**。文件头注释清楚标注 `搬运自 n3d1117/chatgpt-telegram-bot (3.5k⭐) 流式模式`，代码可读性中等偏上，有中文注释和 docstring。1058 行可考虑按 text/voice/streaming 拆分但非紧急。此条目降级为 P3。

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
| 核心服务 | 🟢 运行中 | 7 Bot + FastAPI + Redis (macOS 主节点), Python 进程后台静默运行(无 Dock 图标) |
| 开发工具性能 | 🟢 优化 | OpenCode watcher 扫描文件数从 32.8万 降至 ~5千 (项目瘦身 16GB→6.6GB + 30+条 ignore 规则) |
| LLM 路由 | 🟢 加固 | 主链调整为 SiliconFlow/iflow/Groq/Gemini → Cerebras/OpenRouter/NVIDIA/Volcengine → Mistral/Cohere/GPT_API_Free/g4f，切断 XAPI Claude 空余额兜底 + iflow Key 7天有效期自动检测+告警 |
| 主动智能 | 🟢 运行中 | ProactiveEngine 三步管道 + EventBus触发 + 30min定时检查 + 安静时段过滤(0-7点不推送) |
| AI 记忆 | 🟢 贯通 | SmartMemory→SharedMemory→TieredContextManager user_profile 双通道同步 + 沟通风格偏好确定性注入(onboarding→profile链路修复) |
| 意图识别 | 🟢 加固 | 中文NLP→fast_parse正则→LLM降级分类→Brain任务图，三级漏斗 + 提醒同义词扩展(帮我记住/别忘了/设个闹钟等) |
| 闲鱼客服 | 🟢 加固 | 底价注入+10msg/min限速+prompt注入防护+自动接受价格上限+后台任务异常监控+库存低预警+WS心跳修复+重连熔断器+通知异步化 |
| 交易系统 | 🟢 安全加固 | 22项安全修复 + 风控参数验证 + 日盈亏锁 + SELL风控 + 预算竞态修复 + AI共识度分歧保护 + R4:持仓获取失败返回保守敞口防超额开仓 + 投票弃权机制:超时票不计入统计(timeout 120s+abstained标记+否决逻辑修复) |
| 备用节点 | 🟢 就绪 | 腾讯云 2C2G — 代码已同步, clawbot.service+failover.timer 已部署并验证, 心跳超时120s+3次失败自动接管, Mac恢复后自动退让 |
| 测试通过率 | 🟢 100% | 1339/1341 Python (2项跳过), 0 TypeScript错误, Rust cargo check 零警告。R5新增: 静默异常修复+daily_brief拆分+API输入验证+logger lazy formatting |
| 投资信号追踪 | 🟢 贯通 | record_prediction→validate_predictions→vote_history 三管道全通 |
| 社媒数据分析 | 🟢 贯通 | 浏览器采集→post_engagement存储→/social_report展示→PostTimeOptimizer学习 |
| 闲鱼运营智能 | 🟢 加固 | 利润核算修复+转化标记修复+商品排行+时段分析+转化漏斗+库存低预警 |
| 生活自动化 | 🟢 加固 | 提醒(周期性+同义词触发+北京时区)+记账(收入/支出/月预算/超支告警/月度聚合/ticker防误触发/17个分类含宠物美容保险人情烟酒)+话费水电费余额追踪+定时低余额告警 |
| 购物比价 | 🟢 加固 | 四级降级比价+降价提醒监控(price_watches)+6h定时检查+中文NLP触发+平台可用性标注(淘宝禁用) |
| 代码优化 | 🟢 完成 | 41轮迭代, 全部活跃HI修复, start_trading_system 786→33行, _setup_scheduler 698→48行, 273 个未使用 import 清理 + 6 处 create_task 修复 + 498 处静默异常修复 + 前端 Mock 数据替换 + 11处前端命令命名修复 + 2个死模块接入 + R22深度清理: 15死文件(3.4K行)+38未使用import+28死方法+17重复函数合并 + R22续: 14个未定义名称修复+admin_ids逻辑Bug+PriceAgent/tweepy缺失实现补全+9个死import+5个死依赖 + R23: 19幽灵pyc+5空目录+deploy_bundle_final移出git+33无占位符f-string+config.py提取 + R24: 24个API端点加错误处理+SF-Key竞态锁+6个社交函数async修复+UA常量统一+Twilio/yaml清理 + R25: 6脚本修复+7处Rust安全加固+14个前端any替换 |
| 架构治理 | 🟢 完成 | 全链路: 人格/提示词/装饰器/错误消息/认证/记忆隔离/日志安全/配置校验/备份 |
| API 安全 | 🟢 加固 | X-API-Token + CORS + SSRF + 输入验证 + diagnose=False + RequestSizeLimitMiddleware(10MB) |
| LLM 安全 | 🟢 加固 | Key脱敏(8字符) + 死Key禁用 + 错误清洗 |
| 前端 | 🟢 修复 | 0 TS错误, Tauri shell权限收窄, CSP启用, 状态同步, 内存泄漏修复, JSON.parse 崩溃防护 + 定时器泄漏修复 + 250 行重复代码消除 + Mock 数据替换为 API 调用 + R25: 14个any类型替换为强类型接口+1个未使用导入移除 + P4: 确认对话框(替换browser native)+aria-labels(31个)+Toaster挂载+表单验证(5组件)+空状态(Channels+Plugins)+PageErrorBoundary(14页面)+Settings未保存变更警告 + Dev页面IPC修复+资源仪表盘实现+Channels完整CRUD+CommandPalette真实响应+APIGateway自定义确认框+postcss嵌套修复 + **进化引擎数据映射修复(扁平数组兼容+字段名对齐)+微信渠道配置面板补全+API网关诊断指南** + ControlCenter 773行拆分为8子组件(主文件123行) + CSO审计: sucrase未使用依赖移除+PluginCard forwardRef警告修复+App.tsx注释修正 |
| 部署安全 | 🟢 加固 | VPS systemd加固(non-root+沙箱) + .env排除 + LaunchAgent改进 + deploy_server 默认绑定 127.0.0.1 + compose 资源限制 + CSO审计: Webhook签名hmac.compare_digest防时序攻击 + NewAPI容器cap_drop:ALL/no-new-privileges + .env权限600 + Docker资源调优(Redis 128M/OpenClaw 1G) + 双网络架构(公网+内网隔离) |
| Git 仓库 | 🟢 清理 | 49K 文件从 Git 索引移除 (.venv/node_modules/browser), .gitignore 补充, R21清理24截图+2数据库+残留目录, R23: deploy_bundle_final(4文件)移出git+.gitignore补充, R25: 9101文件移出git(openclaw-npm/node_modules 6139+dist 2896+.openclaw运行时~60+.playwright-cli 2+__pycache__ 1)+.gitignore新增15+规则 |
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
| ~~HI-486~~ | ~~`infra`~~ | ~~`tools/launchagents/*.plist`~~ | ~~macOS 26.4 Sandbox 策略阻止 launchd 子进程读取 ~/Desktop 路径下的文件，6 个 LaunchAgent 全部启动失败 (exit 78/126, 累计失败 1157+ 次)~~ → **已修复 2026-04-13**: ProgramArguments 改为 bash -c exec 间接调用 + 日志路径迁移到 ~/Library/Logs/OpenClaw/ + launcher 脚本命令内联 + 符号链接替换为真实文件。全部 5 个常驻服务恢复正常运行 | 2026-04-13 |
| ~~HI-484~~ | ~~`infra`~~ | ~~`apps/openclaw-manager-src/src/lib`~~ | ~~根目录 `.gitignore` 使用过宽规则 `lib/`，误伤前端 `src/lib/` 源码目录~~ → **已修复 2026-04-12**: `.gitignore` 中 `lib/` 已改为 `/lib/`（仅匹配根目录），`utils.ts` / `tauri.ts` / `logger.ts` 已正常被 Git 跟踪 | 2026-04-10 |
| ~~HI-348~~ | ~~`security`~~ | ~~`.openclaw/agents/`~~ | ~~API密钥曾提交到Git历史~~ → **已修复 2026-04-11**: `git filter-repo` 清理敏感文件历史，.git 从 1.3GB 瘦身到 318MB | 2026-03-28 |
| ~~HI-387~~ | ~~`security`~~ | ~~`config/.env`~~ | ~~50+ 真实密钥曾提交到 Git 历史~~ → **已修复 2026-04-11**: 同上，config/.env 等敏感路径全部从历史中移除。**仍建议轮换密钥** | 2026-04-01 |
| HI-388 | `backend` | `diskcache/pygments` | ~~pip-audit 发现 2 个已知漏洞: diskcache 5.6.3 (CVE-2025-69872)、pygments 2.19.2 (CVE-2026-4539, 修复版本 2.20.0)~~ **pygments 已升级到 2.20.0; diskcache 待上游修复** | 2026-04-01 |
| ~~HI-482~~ | ~~`ai-pool`~~ | ~~`tests/test_litellm_router.py`~~ | ~~本机 Python 3.12 测试环境缺少 `litellm` 依赖~~ → **已解决 2026-04-12**: 创建 `packages/clawbot/.venv` 虚拟环境并安装全部依赖，LiteLLM 路由单测正常运行 | 2026-04-10 |
| ~~HI-483~~ | ~~`infra`~~ | ~~`config/.env`~~ | ~~历史配置中存在重复 `MEM0_API_KEY` 和未接入主流程的 `CLOUDCONVERT_API_KEY`~~ → **已解决 2026-04-10**: 重复项已清理，未接入项降为仅文档登记 | 2026-04-10 |

### 审计进行中

(无)

### 已完成审计

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| ~~HI-485~~ | ~~`audit`~~ | ~~全项目~~ | ~~全量全方位审计~~ → **已完成 2026-04-12**: Phase 1-10 全部完成。后端 1132/1135 通过，前端 tsc 零错误，Rust 零警告。修复 18 处静默吞错 + 安全加固(PIN/SSRF/速率限制/chunked) + 运维加固(Docker网络隔离/非root failover/多阶段构建) + 文档治理(MODULE_REGISTRY 243模块全覆盖/COMMAND_REGISTRY 98命令校准) | 2026-04-10 |

### 🟡 一般

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| ~~HI-487~~ | ~~`backend`~~ | ~~`wechat_bridge.py`~~ | ~~ARCH_LIMIT: 微信仅支持单向推送通知~~ → **描述修正 2026-04-17**: 微信双向对话由 TypeScript 层 `openclaw-weixin` 插件实现（iLink API getUpdates 长轮询），Python 层 `wechat_bridge.py` 仅负责系统通知推送。微信 Bot 基础设施正常运行：token 有效、Gateway 进程在线、sync 持续更新 | 2026-04-17 |
| ~~HI-358~~ | ~~`backend`~~ | ~~多文件~~ | ~~7个>1000行大文件待拆~~ → **已修复 2026-04-11**: 全部7个文件拆分完成 — daily_brief(1158→498), proactive_engine(1016→328), trading_journal(1087→464), risk_manager(1191→854), broker_bridge(1091→762), auto_trader(1055→843), chinese_nlp_mixin(1248→705)。共新建 17 个子模块 | 2026-03-29 |
| ~~HI-381~~ | ~~`backend`~~ | ~~120+文件~~ | ~~内联错误字符串分散~~ → **已解决 2026-04-11**: 重新评估实际为 ~50 处（非 120+），其中 5 条重复消息提取到 `constants.py`（ERR_RISK_NOT_INIT 等 5 个常量），10 处使用点已迁移；其余为上下文相关的唯一消息，保留内联合理 | 2026-03-29 |
| ~~HI-383~~ | ~~`backend`~~ | ~~多文件~~ | ~~HTTP客户端碎片化~~ → **大部分解决 2026-04-11**: HI-463 迁移 20 个文件 35 处调用点到 ResilientHTTPClient（带自动重试+熔断）；剩余 28 处为 COMPLEX（需 cookies/persistent session/sync client），保留原实现合理 | 2026-03-29 |
| ~~HI-384~~ | ~~`backend`~~ | ~~`test_omega_core.py`~~ | ~~Flaky test: `test_investment_full_pipeline` 依赖外部LLM API状态~~ → **已修复 2026-04-11**: mock 隔离 get_context_collector + get_response_synthesizer，消除 LiteLLM Cooldown 依赖 | 2026-03-30 |
| ~~HI-390~~ | ~~`backend`~~ | ~~`social_scheduler.py`~~ | ~~APScheduler job 在线程中通过 `asyncio.run()` 创建临时事件循环，EventBus 事件无法跨循环传播~~ → **已修复 2026-04-11** | 2026-04-01 |
| ~~HI-391~~ | ~~`frontend`~~ | ~~`Plugins`~~ | ~~"安装新插件"和"配置插件"按钮为占位实现~~ → **已修复 2026-04-11**: Rust 层新增 `start/stop/get_status_mcp_plugin` 3 个 Tauri 命令实现真实进程管理（spawn/kill/健康检查）；前端 toggle 连接真实启停；清理 3 条假数据 | 2026-04-01 |
| HI-393 | `infra` | `kiro-gateway` | ~~Kiro Gateway 默认 `PROXY_API_KEY` 为弱密码 `kiro-clawbot-2026`~~ → **已修复**: .env 中已替换为 64 位强随机 token | 2026-04-01 |
| ~~HI-394~~ | ~~`frontend`~~ | ~~`config.rs`~~ | ~~Token 生成函数使用 `/dev/urandom` + 栈地址作为熵源~~ → **已修复 2026-04-11**: 改用 `getrandom` crate 跨平台密码学安全随机源 | 2026-04-01 |
| ~~HI-410~~ | ~~`backend`~~ | ~~`xianyu_apis.py`~~ | ~~XianyuApis httpx.AsyncClient 无自动关闭机制~~ → **已修复 2026-04-11**: XianyuLive 新增 `close()` 方法 + xianyu_main.py finally 块调用 | 2026-04-03 |
| ~~HI-411~~ | ~~`docs`~~ | ~~`MODULE_REGISTRY.md`~~ | ~~7 个核心模块未注册~~ → **已修复 2026-04-11**: 行数从近似值更新为精确值，描述补全 | 2026-04-03 |
| ~~HI-456~~ | ~~`backend`~~ | ~~`brain.py`~~ | ~~`_active_tasks/_pending_callbacks/_pending_clarifications` 共享字典无 asyncio.Lock 保护~~ → **已修复 2026-04-11**: 已有 `self._lock` 现已在所有读写入口加 `async with self._lock` 保护 | 2026-04-03 |
| ~~HI-457~~ | ~~`backend`~~ | ~~`social_tools.py`~~ | ~~`PostTimeOptimizer._engagement_by_hour` 从APScheduler线程和asyncio主线程同时访问~~ → **已修复 2026-04-11**: `_save()` 改用锁内快照写盘 + 单例工厂加双重检查锁 | 2026-04-03 |
| ~~HI-458~~ | ~~`backend`~~ | ~~`social_scheduler.py`~~ | ~~`_current_publish_hour` 在APScheduler线程中写入，在asyncio主线程中读取，无锁保护~~ → **已修复 2026-04-11** | 2026-04-03 |
| ~~HI-459~~ | ~~`backend`~~ | ~~`wechat_bridge.py`~~ | ~~`random.randint` 用于 `X-WECHAT-UIN` 认证header~~ → **已修复 2026-04-11**: 全部替换为 `secrets.randbelow()` | 2026-04-03 |
| ~~HI-460~~ | ~~`backend`~~ | ~~`invest_tools.py`~~ | ~~`_set_config` 事务独立~~ → **已验证 2026-04-11**: `_set_config` 是死代码（无任何调用方），buy/sell 现金事务已在同一 `with self._conn()` 中完成，无风险 | 2026-04-03 |
| ~~HI-461~~ | ~~`backend`~~ | ~~`license_manager.py`~~ | ~~`find_by_buyer()` LIKE 模式未转义通配符~~ → **已修复 2026-04-11**: 增加 `\%`/`\_` 转义 + `ESCAPE '\'` | 2026-04-03 |
| HI-462 | `backend` | 385+处 | 广泛使用 `logger.error(f"...失败: {e}")` 模式 — 异常消息可能包含API URL/密钥/连接字符串。**部分修复 2026-04-11**: 8 个文件 20 处高危调用已用 `scrub_secrets()` 包装 + `utils.scrub_secrets()` 共享函数建立，剩余 ~360 处为低风险（非 API/认证相关） | 2026-04-03 |
| HI-486 | `backend` | `requirements.txt` | stamina 版本约束错误 `~=2.0.0`(PyPI 不存在 2.x 版本, stamina 用 CalVer 从 22.1.0 起) → **已修复**: 改为 `>=24.1.0,<26` | 2026-04-12 |
| HI-487 | `security` | `core/security.py` | PIN 验证使用 `==` 比较存在理论时序攻击风险 → **已修复**: 改为 `hmac.compare_digest()` | 2026-04-12 |
| HI-488 | `deploy` | `heartbeat plist` | 心跳 LaunchAgent plist 硬编码 VPS IP `101.43.41.96` 已入 Git → **已修复**: 改为必填环境变量，无默认值 | 2026-04-12 |
| HI-489 | `deploy` | `kiro-gateway/.env.example` | 示例密码 `my-super-secret-password-123` 可能被用户直接复制使用 → **已修复**: 改为空值 + 强制修改提示 | 2026-04-12 |
| ~~HI-490~~ | ~~`security`~~ | ~~`api/server.py`~~ | ~~FastAPI 无速率限制中间件~~ → **已修复 2026-04-12**: 新增 `RateLimitMiddleware`，基于 IP 滑动窗口限制 60次/分钟，超限返回 429 + Retry-After | 2026-04-12 |
| ~~HI-491~~ | ~~`security`~~ | ~~`api/server.py`~~ | ~~RequestSizeLimitMiddleware chunked 传输可绕过~~ → **已修复 2026-04-12**: 新增流式读取计数，chunked 传输超 10MB 立即返回 413 | 2026-04-12 |
| ~~HI-463~~ | ~~`backend`~~ | ~~20+文件~~ | ~~httpx.AsyncClient per-request创建无重试逻辑~~ → **已修复 2026-04-11**: ResilientHTTPClient API 扩展(follow_redirects+files+data) + 20 个文件 35 处 EASY 调用点迁移完成；剩余 28 处为 COMPLEX（需 cookies/persistent session/sync client），保留原实现 | 2026-04-03 |
| HI-498 | `backend` | `life_automation.py` | 提醒系统 dateparser 时区硬编码为 `America/New_York`，中国用户说"明天下午3点"实际存储为美东时间 → **已修复 2026-04-14**: 改为 `os.environ.get("USER_TIMEZONE", "Asia/Shanghai")`，默认北京时间 | 2026-04-14 |
| HI-499 | `backend` | `chinese_nlp_mixin.py` | "帮我记住/别忘了/设个提醒/定个闹钟"等中文同义表达完全无法触发提醒，只有"提醒我"可用 → **已修复 2026-04-14**: 新增 8 个同义词正则匹配 + nlp_ticker_map 关键词扩展 | 2026-04-14 |
| HI-500 | `backend` | `chinese_nlp_mixin.py` | 记账极简模式 `100 AAPL` 被误识别为"花了100块在AAPL上"（纯大写字母 ticker 无过滤） → **已修复 2026-04-14**: 匹配后检查 note 是否为 1-6 位纯大写字母，是则跳过 | 2026-04-14 |
| HI-501 | `infra` | `run-audit.sh` | 夜间审计 launchd 执行时 `getcwd: Operation not permitted`，0/8 阶段完成 → **已修复 2026-04-14**: SCRIPT_DIR 硬编码项目审计目录，不依赖 launchd 的 WorkingDirectory | 2026-04-14 |
| HI-502 | `backend` | `notify_style.py` | 日报标题双 emoji 叠加 `📢 📊 每日智能日报` → **已修复 2026-04-14**: format_digest 传 icon="" 不再叠加默认 📢 | 2026-04-14 |
| HI-503 | `backend` | `daily_brief.py` | 日报空 heading 节显示 `▸ ` 格式错误 → **已修复 2026-04-14**: 改为 `🏆 闲鱼热销` 有意义的标题 | 2026-04-14 |
| HI-504 | `backend` | `proactive_periodic.py` | ProactiveEngine 凌晨 0-7 点仍推送通知打扰用户 → **已修复 2026-04-14**: 新增 `_is_quiet_hours()` 安静时段过滤 | 2026-04-14 |
| HI-505 | `backend` | `onboarding_mixin.py` | 新用户检测依赖 `get_messages()` 历史消息，DB 重建后所有老用户被误判 → **已修复 2026-04-14**: 改为 shared_memory 持久化标记 `onboarded_{user_id}` | 2026-04-14 |
| HI-506 | `ai-pool` | `litellm_router.py` | iflow Key 7天有效期无任何监控/告警，10 个 TIER_S 模型可能静默失效 → **已修复 2026-04-14**: 新增 `~/.openclaw/iflow_key_timestamp.json` 记录首次使用时间，超 6 天告警并跳过 | 2026-04-14 |
| HI-507 | `backend` | `crawl4ai_engine.py` | 淘宝比价实际不可用（需登录）但没有告知用户 → **已修复 2026-04-14**: 淘宝标记 enabled=False + 比价结果末尾标注实际可用平台 | 2026-04-14 |
| HI-508 | `backend` | `onboarding_mixin.py` | 引导完成后只有"查看全部功能"按钮，无即时体验引导 → **已修复 2026-04-14**: 根据用户选择的兴趣方向添加"立即试试"操作按钮 | 2026-04-14 |
| HI-509 | `backend` | `notify_style.py` | `from typing import ...` 缺少 `List` 导入，导致所有测试在 import 阶段失败 → **已修复 2026-04-15**: 添加 `List` 到 typing imports | 2026-04-15 |
| HI-492 | `infra` | `launchagents/*` | macOS 26.4 Sandbox System Policy 阻止 launchd 读取 ~/Desktop/ 路径下的文件，导致所有 6 个 LaunchAgent 启动失败(exit 78/126) → **已修复 2026-04-13**: ProgramArguments 改为 `/bin/bash -c exec` 间接调用 + 日志路径迁移到 `~/Library/Logs/OpenClaw/` + plist 改为真实文件(非符号链接) | 2026-04-13 |
| HI-493 | `backend` | `scheduler.py` | 笔笔省领券定时任务使用美东时间 08:30(=北京20:30)，导致中午外卖无券可用；且 auto_claim_coupon 无并发锁，曾出现 7 个 mitmdump 同时启动 → **已修复 2026-04-13**: 改为北京时间 07:00 + fcntl.flock 文件锁 | 2026-04-13 |
| HI-494 | `infra` | `run-audit.sh` | 夜间审计被 macOS 延迟触发后，get_remaining_minutes() 算出剩余0分钟直接跳过全部8阶段，产生空报告 → **已修复 2026-04-13**: 新增补跑模式，检测到错过窗口时允许执行120分钟 | 2026-04-13 |
| ~~HI-495~~ | ~~`ai-pool`~~ | ~~`litellm_router.py`~~ | ~~LLM 路由 122 部署中仅 3/14 provider 可用(Groq/Cerebras/Mistral)，SiliconFlow全军覆没(auth_error)、OpenRouter额度耗尽(429)、Gemini/NVIDIA模型名过时、Cohere/iflow/gpt_free/kiro/volcengine 认证或服务异常~~ → **已诊断并修复 2026-04-13**: 重新测试后确认 6/16 正常(含 SF 付费/NVIDIA/Cohere)。g4f 改为读取 G4F_API_KEY。SF 免费/Gemini/iflow/Volc/GPT_API_Free/Kiro 等均为平台侧余额耗尽、模型下线或 token 过期，代码本身逻辑正确。 | 2026-04-13 |
| ~~HI-496~~ | ~~`infra`~~ | ~~`heartbeat-sender`~~ | ~~心跳发送进程停摆 6 天(自4月7日)，launchd agent 已注册但未活跃，VPS failover 无法检测主节点存活~~ → **已修复 2026-04-13**: HI-492 解决后心跳进程已自动恢复运行（PID 存活），日志显示成功发送心跳；因本地网络问题导致间歇性 SSH 失败，进程机制正常。 | 2026-04-13 |
| ~~HI-497~~ | ~~`trading`~~ | ~~`_scheduler_daily.py`~~ | ~~IBKR Gateway 未运行(127.0.0.1:4002 连接拒绝)，IBKR_START_CMD 被白名单拦截无法自动启动，交易调度器每3分钟重连失败造成日志洪泛~~ → **已修复 2026-04-13**: 为 `_ibkr_health_check` 引入 `_ibkr_health_fail_count`，将无脑 3 分钟一刷的错误日志降频为第 1 次及每 10 次(约30分钟)提示，并将检测间隔通过 `IBKR_HEALTH_CHECK_INTERVAL_MIN` 暴露为可配置。 | 2026-04-13 |
| ~~HI-520~~ | ~~`trading`~~ | ~~`freqtrade_bridge.py`~~ | ~~BUG: `confirm_trade_entry()` 传 dict 给 `check_trade()` 而非关键字参数，且用 `.get("approved")` 而非 `.approved` 属性访问 RiskCheckResult~~ → **已修复 2026-04-18**: 改为关键字参数调用 + `.approved` 属性 + 默认 3% 止损 | 2026-04-18 |
| ~~HI-521~~ | ~~`trading`~~ | ~~`brain_exec_invest.py`~~ | ~~BUG: `_exec_risk_check()` 两处 `check_trade()` 调用不传 `stop_loss`(默认0)，导致 `StopLossValidator` 拒绝所有 BUY 交易~~ → **已修复 2026-04-18**: 补传 `stop_loss=entry_price*0.97`(默认3%止损)，优先读取 params 中用户指定值 | 2026-04-18 |
| HI-522 | `trading` | `risk_manager.py` | TECH_DEBT: `check_trade()` 读取 `_today_pnl/_today_trade_count` 等共享状态无锁保护，多协程并发交易可能出现竞态条件 | 2026-04-18 |
| HI-523 | `trading` | `risk_manager.py` | ARCH_LIMIT: SELL 方向交易几乎不做风控检查（仅持仓验证），缺少卖空风控、止损验证等 | 2026-04-18 |
| HI-524 | `trading` | `risk_manager.py` | ARCH_LIMIT: 新账户首笔交易时 `_today_pnl=0 / _today_trade_count=0 / positions=[]`，VaR 保护因无持仓数据而完全失效 | 2026-04-18 |
| HI-525 | `ai-pool` | `litellm_router.py` + `config/llm_routing.json` | TECH_DEBT: JSON 配置与硬编码完全漂移 — iflow_unlimited 的 URL 和模型名不一致，需确认统一切换策略 (R2.25/R2.29) | 2026-04-18 |
| HI-526 | `backend` | `src/` 全目录 | TECH_DEBT: 代码库 59 个静默异常 (`except: pass` / `except Exception: pass`)，最危险的 3 个在 `trading_pipeline.py` 已修复，剩余 56 个需逐步改造 (R2.44) | 2026-04-18 |
| HI-527 | `backend` | `src/` 全目录 | TECH_DEBT: 8 个 `asyncio.create_task()` 未设置 `done_callback`，异常静默吞掉形成幽灵任务 (R2.45) | 2026-04-18 |
| HI-528 | `backend` | SQLite 全部 6 实例 | TECH_DEBT: 无数据库自动备份策略，6 个 SQLite 文件（shared_memory/trading_journal/xianyu 等）无定期备份 (R2.36) | 2026-04-18 |
| HI-529 | `backend` | `src/bot/cmd_*.py` | TECH_DEBT: 98 个 `cmd_` 命令处理函数中 72 个(73%)缺少 try/except 错误处理，异常直接抛到全局 error handler (R3.41-R3.45) | 2026-04-19 |
| HI-530 | `backend` | `src/bot/workflow_mixin.py` | TECH_DEBT: 25 个方法中 22 个是死代码(从未被任何调用方引用)，8 个标注 "not yet implemented" 的 stub 方法。整个链式讨论工作流基础设施搭建了但未接入消息管道 (R3.31-R3.35) | 2026-04-19 |
| HI-531 | `backend` | `cmd_basic/help_mixin.py` | TECH_DEBT: /help 菜单有 30 个注册命令未被任何分类覆盖（/calc, /chart, /drl, /factors, /icancel, /tts, /novel, /evolution, /coupon 等），用户无法通过帮助菜单发现这些命令 (R3.04) | 2026-04-19 |
| HI-535 | `backend` | `src/modules/investment/` | TECH_DEBT: AI 投票系统只追踪共识决策的准确率，不追踪单个模型的独立预测准确率，无法评估哪个 AI 分析师表现最好 (R4.03) | 2026-04-19 |
| HI-536 | `backend` | `invest_tools.py` | TECH_DEBT: yfinance 60s 缓存过期后若新请求失败，返回错误而非降级到过期缓存数据——缺少 stale-data fallback (R4.04) | 2026-04-19 |
| HI-537 | `backend` | `freqtrade_bridge.py` | TECH_DEBT: `inject_clawbot()` 从未在启动时自动调用，freqtrade 集成路径实际为死代码；策略类正确但从未被连接 (R4.06) | 2026-04-19 |
| HI-538 | `backend` | `src/execution/social/` | TECH_DEBT: 多平台发布使用 if/elif 链而非适配器模式，Weibo/Discord/WeChat 定义了限制参数但无实际发布实现；添加新平台需改多个文件 (R4.13) | 2026-04-19 |
| HI-539 | `backend` | `drafts.py` + `social_scheduler.py` | TECH_DEBT: 存在两套平行的草稿系统——Telegram 命令用的内存 `_draft_store` 重启即丢失，自动驾驶用的 JSON 文件持久化。两者数据不同步 (R4.16) | 2026-04-19 |
| HI-540 | `backend` | `price_engine.py` vs `brain_exec_life.py` | TECH_DEBT: 交互式比价用四级降级链(Tavily→crawl4ai→Jina→LLM)，但定时价格监控 6h 检查用的是完全不同的简单 HTML 爬虫引擎(SMZDM+JD)，两个引擎能力差异大 (R4.28) | 2026-04-19 |
| HI-541 | `backend` | `nlp_ticker_map.py` | TECH_DEBT: 1-5字母 ticker 解析无常见英语单词黑名单(AT/IT/TO/BE/GO 等可能被误识别为股票代码) (R4.30) | 2026-04-19 |
| HI-542 | `backend` | `notifications.py` + `event_bus.py` | TECH_DEBT: 通知系统无 shutdown flush 机制——进程被 kill 时正在发送的通知会静默丢失；EventBus 也没有 drain pending tasks (R4.40) | 2026-04-19 |

### 🔵 低优先

| ID | 领域 | 模块 | 描述 | 发现日期 |
|----|------|------|------|----------|
| ~~HI-464~~ | ~~`backend`~~ | ~~`proactive_engine.py`~~ | ~~`_sent_log/_recent_notifications` 字典无锁~~ → **已修复 2026-04-11**: 新增 `asyncio.Lock`，evaluate/record_sent 加锁保护 | 2026-04-03 |
| ~~HI-465~~ | ~~`backend`~~ | ~~`news_fetcher.py`~~ | ~~`_seen_titles` 集合无界增长+无锁~~ → **已修复 2026-04-11**: 新增 `asyncio.Lock`；500 上限截取已有注释说明 | 2026-04-03 |
| ~~HI-466~~ | ~~`backend`~~ | ~~`error_handler.py`~~ | ~~`ErrorThrottler._seen/_counts` + `ErrorHandler._total_errors` 统计计数器无锁~~ → **已修复 2026-04-11**: ErrorThrottler + ErrorHandler 分别新增 `asyncio.Lock`，report() 锁保护计数和去重 | 2026-04-03 |
| ~~HI-467~~ | ~~`backend`~~ | ~~`multi_bot.py`~~ | ~~`_live_context_cache` TTL检查与写入无锁~~ → **已修复 2026-04-11**: 新增 `threading.Lock`，TTL 检查/缓存写入原子化 | 2026-04-03 |

---

## 已解决 (RESOLVED)

| ID | 领域 | 模块 | 描述 | 解决方案 | 解决日期 | CHANGELOG |
|----|------|------|------|----------|----------|-----------|
| HI-532 | `backend` | `callback_mixin.py` | 🟠 HIGH: 回调按钮调用 cmd_ 命令时 `update.message` 为 None 导致 AttributeError — handle_card_action_callback 无 try/except 保护(5处 cmd_ 调用)，handle_notify_action_callback 有 try/except 但错误消息为技术堆栈 | 新增 `_safe_cmd_from_callback()` 辅助函数统一包裹所有回调→命令调用，捕获 AttributeError 并用 query.message 回复友好提示 | 2026-04-19 | R3 Bot命令层审计 |
| HI-533 | `backend` | `help_mixin.py` | 🟡 MEDIUM: /help 投资分析分类中 /invest 描述为"5 位 AI 协作分析"，实际为 6 位 | 修正为"6 位 AI 协作分析" | 2026-04-19 | R3 Bot命令层审计 |
| HI-534 | `backend` | `workflow_mixin.py` | 🟡 MEDIUM: `_pick_workflow_bot()` 兜底返回值类型不一致 — 正常路径返回 `(candidates, bot_id)` 元组，所有 bot 被排除时返回 `self.bot_id` 字符串，调用方解构会崩溃 | 兜底路径改为 `return None, self.bot_id` 保持元组类型一致 | 2026-04-19 | R3 Bot命令层审计 |
| HI-510 | `backend` | `weekly_report.py` | 🔴 CRITICAL: 周报导入路径错误 — `from src.content_pipeline` 应为 `from src.execution.social.content_pipeline`，导致周报生成必然崩溃 | 修正导入路径为正确的模块位置 | 2026-04-17 | CSO全量安全审计 |
| HI-511 | `backend` | `api/routers/xianyu.py` | 🔴 CRITICAL: 闲鱼路由导入不存在的 `XianyuBot` 类，服务启动时 ImportError | 替换为 `XianyuContextManager` 直接查询 SQLite | 2026-04-17 | CSO全量安全审计 |
| HI-512 | `deploy` | `docker-compose.yml` | 🔴 CRITICAL: Docker 资源超配(Redis 512M/OpenClaw 2G) + `internal: true` 阻断容器互联网访问 | Redis 128M/OpenClaw 1G + 移除 internal + 双网络架构 | 2026-04-17 | CSO全量安全审计 |
| HI-513 | `infra` | `Makefile` | 🔴 CRITICAL: 硬编码 `/usr/bin/python3` 路径在 macOS/brew 环境不存在 | 自动检测: `which python3 \|\| which python` | 2026-04-17 | CSO全量安全审计 |
| HI-514 | `security` | `deploy_server.py` | 🟠 HIGH: Webhook 签名验证使用 `==` 比较存在时序攻击漏洞 | 改为 `hmac.compare_digest()` 常量时间比较 | 2026-04-17 | CSO全量安全审计 |
| HI-515 | `deploy` | `docker-compose.newapi.yml` | 🟠 HIGH: NewAPI 容器无安全加固，默认 root + 全权限运行 | 添加 `cap_drop: ALL` + `security_opt: no-new-privileges:true` | 2026-04-17 | CSO全量安全审计 |
| HI-516 | `frontend` | `openclaw-manager-src` | 🟠 HIGH: 未使用的 `sucrase` 依赖增加供应链攻击面 | 移除 sucrase 依赖 | 2026-04-17 | CSO全量安全审计 |
| HI-517 | `frontend` | `App.tsx` | 🟡 MEDIUM: 注释与实际代码行为不符，产生误导 | 修正注释为准确描述 | 2026-04-17 | CSO全量安全审计 |
| HI-518 | `frontend` | `Store/index.tsx` | 🟡 MEDIUM: PluginCard 触发 React forwardRef 废弃警告 | 修复组件定义消除警告 | 2026-04-17 | CSO全量安全审计 |
| HI-519 | `security` | `.env` | 🟡 MEDIUM: .env 文件权限未收紧，同机其他用户可读取密钥 | 所有 .env 权限设为 600 | 2026-04-17 | CSO全量安全审计 |
| HI-456 | `backend` | `brain.py` | 共享字典 `_active_tasks/_pending_callbacks/_pending_clarifications` 无锁保护 | 已有 `self._lock` 现在全部读写入口加 `async with self._lock` 保护；`get_active_tasks` 改用 `list()` 快照迭代；延迟清理改用 async task + lock | 2026-04-11 | 价值位阶审计 Tier 2 |
| HI-457 | `backend` | `social_tools.py` | PostTimeOptimizer `_save()` 在锁外读取共享数据 + 单例工厂无锁 | `record_engagement` 在锁内拍快照传给 `_save()`；`_save()` 支持传入快照或自行加锁；`get_post_time_optimizer()` 加双重检查锁 | 2026-04-11 | 价值位阶审计 Tier 2 |
| HI-464 | `backend` | `proactive_engine.py` | `_sent_log/_recent_notifications` 无 asyncio.Lock | 新增 `self._lock = asyncio.Lock()`，evaluate 频率检查和 record_sent 均加锁保护 | 2026-04-11 | 价值位阶审计 Tier 2 |
| HI-465 | `backend` | `news_fetcher.py` | `_seen_titles` 无锁 + 无界增长 | 新增 `asyncio.Lock`；500 上限截取保留最近 200 条并添加注释说明 | 2026-04-11 | 价值位阶审计 Tier 2 |
| HI-466 | `backend` | `error_handler.py` | ErrorThrottler/ErrorHandler 计数器无锁 | ErrorThrottler + ErrorHandler 分别新增 `asyncio.Lock`；`report()` 用 `async with self._lock` 保护计数和去重；`cleanup()` 用 `list()` 快照迭代 | 2026-04-11 | 价值位阶审计 Tier 2 |
| HI-467 | `backend` | `multi_bot.py` | `_live_context_cache` TTL 检查与写入无锁 | 新增 `threading.Lock`（PTB concurrent_updates=True 下为多线程），TTL 读取和缓存写入均在锁内执行 | 2026-04-11 | 价值位阶审计 Tier 2 |
| HI-393 | `infra` | `kiro-gateway/.env` | 默认弱密码 `kiro-clawbot-2026` | .env 中已替换为 64 位强随机 hex token；config.py 默认值为空字符串（未设置时拒绝所有请求） | 2026-04-11 | 价值位阶审计 Tier 3 |
| HI-394 | `frontend` | `config.rs` | Token 生成使用 `/dev/urandom` + 栈地址，Windows 不可用 | 改用 `getrandom::getrandom()` 密码学安全跨平台随机源，删除手动读文件+时间戳兜底 | 2026-04-11 | 价值位阶审计 Tier 3 |
| HI-410 | `xianyu` | `xianyu_apis.py`+`xianyu_live.py` | httpx.AsyncClient 无自动关闭，TCP 连接泄漏 | XianyuLive 新增 `close()` 方法调用 `api.close()`；xianyu_main.py 在 finally 块中调用 | 2026-04-11 | 价值位阶审计 Tier 3 |
| HI-390 | `backend` | `social_scheduler.py` | APScheduler job 创建临时事件循环，EventBus 事件无法跨循环传播 | `start()` 中捕获主事件循环引用并更新类变量；`_run_async()` 使用 `run_coroutine_threadsafe()` 调度到主循环，降级回退 `asyncio.run()` | 2026-04-11 | social_scheduler 稳定性修复 |
| HI-458 | `backend` | `social_scheduler.py` | `_current_publish_hour` 在APScheduler线程和主线程间无锁保护 | 新增 `_publish_hour_lock = threading.Lock()` 类变量，所有读写 `_current_publish_hour` 的位置加锁保护 | 2026-04-11 | social_scheduler 稳定性修复 |
| HI-471 | `frontend` | `Dev/index.tsx` | Dev页面action按钮绑定的 `send_telegram_command` 命令不存在 | 替换为实际可用的 `api.omegaProcess` | 2026-04-09 | 桌面端深度审计 |
| HI-472 | `infra` | `diagnostics.rs` | 资源仪表盘数据缺失，`get_system_resources` Tauri命令未实现 | 完整实现系统资源拉取命令并在 main.rs 中注册 | 2026-04-09 | 桌面端深度审计 |
| HI-473 | `frontend` | `Channels/index.tsx` | 渠道管理页面为空壳占位符 | 实现完整的消息渠道增删改查 CRUD 界面 | 2026-04-09 | 桌面端深度审计 |
| HI-474 | `xianyu` | `xianyu_admin.py` | 9 个后端数据库管理端点可能抛出未格式化的内部500异常 | 添加全面的 `try/except Exception as e` 并返回标准错误格式 | 2026-04-09 | 桌面端深度审计 |
| HI-475 | `security` | `server.py` | 全局缺乏请求体大小限制，存在大载荷 DoS 风险 | 注册 `RequestSizeLimitMiddleware`，限制 10MB 请求 | 2026-04-09 | 桌面端深度审计 |
| HI-476 | `frontend` | `CommandPalette.tsx` | 4个快捷操作返回数据不显示，统一直出"完成"导致无法区分状态 | 将执行结果文本绑定到 toast 展现真实 API 响应数据 | 2026-04-09 | 桌面端深度审计 |
| HI-477 | `frontend` | `APIGateway/index.tsx` | 使用了阻断式的 `window.confirm` 原生对话框破坏 UI 一致性 | 替换为系统自定义的 `ConfirmDialog` 组件 | 2026-04-09 | 桌面端深度审计 |
| HI-478 | `frontend` | `postcss.config.js` | Vite构建因为Tailwind的 `@apply` 在嵌套CSS中失败 | 补全 `tailwindcss/nesting` 插件支持 | 2026-04-09 | 桌面端深度审计 |
| HI-479 | `frontend` | `Evolution/index.tsx` | **进化引擎数据全部不显示** — 后端返回扁平JSON数组，前端按 `{proposals:[]}` 解构导致51个真实提案和11个能力缺口映射为空；`last_scan_time` vs `last_scan` 字段名不匹配导致扫描时间不显示；`by_status` 嵌套结构未映射导致审批统计丢失 | 增加 `Array.isArray()` 兼容检测，扁平数组和包装对象两种格式均正确解构；`last_scan_time` 纳入映射链；`by_status` 嵌套字段透传 | 2026-04-09 | 进化引擎数据修复 |
| HI-480 | `frontend` | `Channels/index.tsx` | 微信渠道配置面板为空 — `fields: []` 导致编辑时只显示"此渠道主要通过命令行配置"，无实际配置入口 | 添加桥接方式/Puppet类型/自动通过好友/管理员微信ID 4个配置字段；新增微信和WhatsApp接入说明引导卡片 | 2026-04-09 | 进化引擎数据修复 |
| HI-481 | `frontend` | `APIGateway/index.tsx` | API网关离线提示过于笼统 — 只列出"可能的原因"但不指导如何解决，用户无法自行排查 | 改为分步排查指南（含Docker Desktop下载链接+终端启动命令），精确定位Docker未安装/未启动/容器未运行等具体原因 | 2026-04-09 | 进化引擎数据修复 |

| ID | 领域 | 模块 | 描述 | 解决方案 | 解决日期 | CHANGELOG |
|----|------|------|------|----------|----------|-----------|
| HI-468 | `xianyu` | `xianyu_live.py` | `cookie_health_loop` 的 `_cookie_ok` 标志逻辑缺陷 — 首次自动登录失败后 `_cookie_ok=False` 永远阻止重新触发登录 | 去掉 `and self._cookie_ok` 条件，只要连续失败>=2 且不在冷却期就触发登录; Cookie 失效时检查间隔从 600s 缩短到 60s; 增加空 Cookie 直接检测 | 2026-04-07 | 闲鱼自动登录修复 |
| HI-469 | `xianyu` | `xianyu_live.py` | `cookie_health_loop` 在 WS 连接内部启动 — WS 连不上时 Cookie 检查永远无法运行 | 提升为独立任务在 `run()` 开头启动，不再随 WS 断开取消 | 2026-04-07 | 闲鱼自动登录修复 |
| HI-470 | `xianyu` | `xianyu_main.py` | Cookie 为空时 `sys.exit(1)` 退出 — 进程无法自愈 | 改为弹出浏览器登录窗口，失败也不退出，进入后台重试循环 | 2026-04-07 | 闲鱼自动登录修复 |
| HI-435 | `security` | `cost_analyzer.py` | CRITICAL: `with sqlite3.connect() as conn:` 不关闭连接 — 每次API调用泄漏一个SQLite连接 | 6个方法全部改为显式 `try/finally + conn.close()` | 2026-04-03 | 第六轮深层审计 |
| HI-436 | `security` | `license_manager.py` | CRITICAL: 密码存储使用裸SHA-256无盐 — 彩虹表秒破 | 升级为 PBKDF2+随机盐(10万次迭代); 旧格式自动检测并透明升级 | 2026-04-03 | 第六轮深层审计 |
| HI-437 | `backend` | `structured_llm.py` | CRITICAL: `_instructor_client_cache` 缓存无锁 — 并发创建重复instructor客户端 | 增加 `threading.Lock` 双重检查锁保护 | 2026-04-03 | 第六轮深层审计 |
| HI-438 | `backend` | `broker_selector.py` | HIGH: `get_ibkr()` 单例创建无线程安全 — APScheduler线程可能创建多个IB连接 | 增加 `threading.Lock` 双重检查锁 | 2026-04-03 | 第六轮深层审计 |
| HI-439 | `trading` | `invest_tools.py` | HIGH: `buy()/sell()` 现金读取和更新在不同事务中 — 可能 double-spend | 合并到同一个 `with self._conn()` 事务块 | 2026-04-03 | 第六轮深层审计 |
| HI-440 | `security` | `security.py` | HIGH: 旧格式SHA-256 PIN验证后不自动升级 — 旧PIN永远停留在弱哈希 | 验证成功后自动用PBKDF2+盐重新哈希并覆盖文件 | 2026-04-03 | 第六轮深层审计 |
| HI-441 | `security` | `xianyu/utils.py` | HIGH: `random` 模块生成消息ID/设备ID/UUID — Mersenne Twister可预测 | 全部迁移到 `secrets` 模块; UUID改为 `secrets.token_hex(16)` | 2026-04-03 | 第六轮深层审计 |
| HI-442 | `security` | `xianyu_live.py` | HIGH: License Key 完整明文记录到日志 | 脱敏为 `key[:4]...key[-4:]` | 2026-04-03 | 第六轮深层审计 |
| HI-443 | `security` | `order_notifier.py` | HIGH: 通知消息包含明文密码和完整License Key | 密码脱敏为 `password[:2]***`; Key脱敏为 `key[:4]...key[-4:]` | 2026-04-03 | 第六轮深层审计 |
| HI-444 | `security` | `bash_tool.py` | HIGH: `workdir` 参数无限制 — 可执行 `cat /etc/passwd` | `os.path.realpath()` + 项目根目录前缀检查 | 2026-04-03 | 第六轮深层审计 |
| HI-445 | `security` | `comfyui_client.py` | HIGH: 远程服务器filename无净化 — `../../` 可写任意路径 | `os.path.basename()` 剥离目录组件 | 2026-04-03 | 第六轮深层审计 |
| HI-446 | `security` | `code_tool.py` | HIGH: RestrictedPython缺失时静默降级 + 固定临时文件名竞态 | 缺失时拒绝执行; 临时文件名用UUID | 2026-04-03 | 第六轮深层审计 |
| HI-447 | `security` | `file_tool.py` | MEDIUM: 用户/LLM提供的正则无长度限制 — ReDoS风险 | 200字符上限 + try/except编译保护 | 2026-04-03 | 第六轮深层审计 |
| HI-448 | `backend` | `llm_cache.py` | MEDIUM: diskcache单例创建无锁 — 并发创建多个SQLite缓存 | `threading.Lock` 双重检查锁 | 2026-04-03 | 第六轮深层审计 |
| HI-449 | `backend` | `event_bus.py` | MEDIUM: `publish()` 迭代handlers时可被 `subscribe()` 并发修改 | 迭代前 `list()` 快照 | 2026-04-03 | 第六轮深层审计 |
| HI-450 | `backend` | `shared_memory.py` | MEDIUM: 重复 `close()` 方法定义 — 第一个被第二个覆盖 | 删除第一个; 第二个增加try/except | 2026-04-03 | 第六轮深层审计 |
| HI-451 | `backend` | `history_store.py` | MEDIUM: 重复 `close()` 方法定义 — 同上 | 同上 | 2026-04-03 | 第六轮深层审计 |
| HI-452 | `backend` | `execution/_db.py` | LOW: `get_conn()` 异常时无显式rollback | 增加 `except: conn.rollback(); raise` | 2026-04-03 | 第六轮深层审计 |
| HI-453 | `security` | `ocr_processors.py` | MEDIUM: `.format()` 处理OCR文本 — `{variable}` 模板注入 | 改为 `.replace()` | 2026-04-03 | 第六轮深层审计 |
| HI-454 | `security` | `intent_parser.py` | MEDIUM: `.format()` 处理用户消息 — 同上 | 改为 `.replace()` | 2026-04-03 | 第六轮深层审计 |
| HI-455 | `backend` | `test_bash_tool.py` | 测试更新: workdir测试使用项目内目录+新增越界拒绝测试 | 更新测试适配新安全限制 | 2026-04-03 | 第六轮深层审计 |
| HI-412 | `security` | `shared_memory.py`+`smart_memory.py` | 记忆存储跨用户隔离漏洞: search(chat_id=None)搜全表+SmartMemory不传chat_id+get_context_for_prompt无用户过滤 | search/remember/get_context_for_prompt 全部增加 chat_id 隔离; 测试更新验证新行为 | 2026-04-03 | 全量审计P0 |
| HI-413 | `security` | `kiro-gateway/main.py` | CORS allow_methods/allow_headers=[\"*\"] 过于宽松 | 收窄为 GET/POST/OPTIONS + 4个具体Header | 2026-04-03 | 全量审计P0 |
| HI-414 | `security` | `api/server.py` | 内部 API 文档在生产环境可访问 | 生产环境 docs_url=None | 2026-04-03 | 全量审计P0 |
| HI-415 | `security` | `jina_reader.py` | 用户传入URL无SSRF检查 | 增加 check_ssrf(url) 前置检查 | 2026-04-03 | 全量审计P0 |
| HI-416 | `security` | `broker_bridge.py` | IBKR_START_CMD环境变量可执行任意命令 | 增加可执行文件名白名单校验 | 2026-04-03 | 全量审计P0 |
| HI-382 | `backend` | 多文件 | P7: 硬编码 LLM 模型名散落在多个文件中 | 统一到 config 配置 | 2026-03-29 | R22续审计 |
| HI-386 | `frontend` | `App.tsx` | Toaster/toast 死代码 | Toaster 挂载+toast 迁移+死文件删除 | 2026-03-30 | P4审计 |
| HI-389-b | `backend` | `xianyu_apis.py` | 闲鱼 API 同步 requests 阻塞事件循环 | 迁移到 httpx.AsyncClient | 2026-04-01 | 闲鱼审计 |
| HI-392 | `backend` | 多文件(5个) | 疑似未使用 pip 依赖 | 验证全部在用(延迟导入+graceful degradation) | 2026-04-01 | 闲鱼审计 |
| HI-395 | `frontend` | `service.rs/installer.rs` | 7处 std::thread::sleep 阻塞 tokio 工作线程 | 替换为 tokio::time::sleep | 2026-04-01 | 闲鱼审计 |
| HI-396 | `infra` | `launchagents` | macOS BTM 屏蔽 LaunchAgent | Tauri APP bash launcher 降级路径; **macOS 26.4 复发**: `com.apple.provenance` 属性导致退出码 126/78, 改用 heredoc stdin 管道绕过 | 2026-04-01 | 闲鱼审计 → 2026-04-06 二次修复 |
| HI-408 | `backend` | `multi_main.py` | Bot 心跳发送依赖 `updater.running` 条件 — 网络波动时所有 Bot 同时丢失心跳触发告警风暴 | 移除 `updater.running` 条件，改为只要 `bot.app` 存在即发心跳；告警消息增加每个 Bot 的距上次心跳秒数和连续错误数 | 2026-04-01 | 心跳机制修复 |
| HI-409 | `xianyu` | `xianyu_live.py` + `xianyu_login.py` | Cookie 彻底过期后无法自救 — 需手动更新 Cookie | Playwright 浏览器自动登录工具: Cookie 过期时自动弹出浏览器→用户扫码→Cookie 自动提取写入 .env→热更新闲鱼进程。带 30 分钟冷却防重复弹出 | 2026-04-01 | 闲鱼自动登录 |
| HI-398 | `xianyu` | `xianyu_live.py` | 心跳超时不触发重连 — heartbeat_loop 超时后只 break 自身循环，不关闭 WS，导致连接僵死 | 超时后主动 `ws.close()` + 设置 `restart_flag` 强制重连 | 2026-04-01 | 闲鱼全面审计 |
| HI-399 | `xianyu` | `xianyu_live.py` | Token 刷新强制断开 WS — 每小时刷新 Token 时主动关闭连接，导致每天 24 次不必要的重连 | 移除 `ws.close()` 调用，仅设置 `restart_flag` 让主循环在消息处理完成后重连 | 2026-04-01 | 闲鱼全面审计 |
| HI-400 | `xianyu` | `xianyu_live.py` | 重连无上限保护 — `while True` 无熔断器，Cookie 失效后无限重试 | 添加熔断器: 连续失败 50 次后暂停 10 分钟冷却，冷却后自动重试 | 2026-04-01 | 闲鱼全面审计 |
| HI-401 | `xianyu` | `xianyu_live.py` | 重连告警被稀释 — 每次成功后计数清零，连续 5 次以上才告警一次 | 改为每 5 次连续失败告警一次(可重复)，增加累计总次数监控 | 2026-04-01 | 闲鱼全面审计 |
| HI-402 | `xianyu` | `xianyu_live.py` | 后台任务 cancel 后未 await — 任务清理代码可能未完成即开始下次连接 | `task.cancel()` 后用 `asyncio.gather(..., return_exceptions=True)` 等待清理完成 | 2026-04-01 | 闲鱼全面审计 |
| HI-403 | `xianyu` | `order_notifier.py` | 同步 `requests.post` 阻塞事件循环 — 异步场景首次调用仍会阻塞 | 全量迁移到 httpx: 异步场景用 `httpx.AsyncClient`，同步场景用 `httpx.Client` | 2026-04-01 | 闲鱼全面审计 |
| HI-404 | `xianyu` | `xianyu_apis.py` | `.env` 写入非原子操作 — 崩溃时可能损坏文件 | 改为 tempfile + `os.replace()` 原子写入 | 2026-04-01 | 闲鱼全面审计 |
| HI-405 | `backend` | `message_mixin.py` | 死引用 `xianyu_live_session` — 模块不存在，每次启动触发 ImportError (被 try/except 静默) | 移除死引用，添加注释说明闲鱼作为独立进程运行 | 2026-04-01 | 闲鱼全面审计 |
| HI-406 | `xianyu` | `xianyu_live.py` | 底价注入死代码 — `if item_id and not floor` 条件永远与上方查询结果一致，重复查询无意义 | 修正逻辑: 改为 `if item_id and floor is not None` 直接使用已查询的结果 | 2026-04-01 | 闲鱼全面审计 |
| HI-407 | `backend` | `cmd_xianyu_mixin.py` | 未使用的 `import subprocess` — 所有子进程调用已迁移为 `asyncio.create_subprocess_exec` | 移除未使用的 import | 2026-04-01 | 闲鱼全面审计 |
| HI-349 | `security` | `code_tool.py` + `bash_tool.py` | Python/Node.js代码沙箱可被CPython内部机制绕过 | code_tool.py 重写: 全部Python执行移至subprocess+resource.setrlimit(CPU 30s/MEM 256MB/NPROC=0/FSIZE 1MB)+进程组隔离+环境变量白名单; bash_tool.py: _make_safe_env()过滤敏感环境变量; RestrictedPython仅做AST预检不执行 | 2026-03-31 | P6安全加固 |
| HI-388 | `security` | `life_automation.py` | `shortcuts run` 命令仅做正则校验无白名单 — 恶意快捷指令名可能绕过 | 添加 _SHORTCUT_WHITELIST frozenset 白名单，仅允许预定义快捷指令名称执行，未在白名单中的指令被拦截并记录日志 | 2026-03-31 | P6安全加固 |
| HI-389 | `security` | `omega.py` | `/tools/jina-read` SSRF 防护未处理 DNS 重绑定攻击 | 添加 socket.getaddrinfo DNS 预解析，对所有解析到的 IP 逐一检查 is_private/is_loopback/is_link_local，域名解析失败返回 400 | 2026-03-31 | P6安全加固 |
| HI-277 | `deploy` | VPS failover | Mac 恢复后无 VPS 退让机制 — 可能导致双节点同时运行 Bot | `vps_failover_check.sh` 第59-63行已实现退让逻辑: 心跳有效时自动 `systemctl stop clawbot`; HI-344已完成部署 | 2026-03-31 | 活跃问题复核 |
| HI-278 | `deploy` | VPS failover | failover timer 脚本原不在 Git 仓库 — VPS 重装后机制丢失 | 脚本已在 `scripts/vps_failover_check.sh` + systemd 配置在 `scripts/systemd/`; `deploy_vps.sh` 自动部署 | 2026-03-31 | 活跃问题复核 |
| HI-390 | `trading` | `trading_journal.py` | SQLite `date()` 将 ET 时区 ISO 字符串转为 UTC 日期 — 晚 8 点后平仓的交易在当日统计中消失 | 全部 9 处 `date(exit_time/prediction_time)` 替换为 `substr(...,1,10)` 直接提取 ET 本地日期 | 2026-03-30 | P2架构审计 |
| HI-385 | `backend` | `data_providers.py` | 5处类型注解引用未定义的 `pd` (pandas) | 添加 `from typing import TYPE_CHECKING` + `if TYPE_CHECKING: import pandas as pd` 条件导入 | 2026-03-31 | P2续审计 |

| ID | 领域 | 模块 | 描述 | 解决方案 | 解决日期 | CHANGELOG |
|----|------|------|------|----------|----------|-----------|
| HI-387 | `security` | `auth.py` | `log_token_status()` 将 `0.0.0.0` 列为安全主机 — 绑定 0.0.0.0 时不触发 CRITICAL 警告 | 从安全主机元组中移除 `0.0.0.0`，仅保留 `127.0.0.1` 和 `localhost` | 2026-03-30 | P0安全审计 |
| HI-377 | `backend` | `social_browser_worker.py` | macOS字体路径硬编码 — Linux部署必崩 | `_detect_font_path()` 自动检测macOS/Linux字体+`OPENCLAW_FONT_PATH` env var覆盖 | 2026-03-29 | R26 |
| HI-376 | `infra` | 7个Rust文件 | 文件级 `#![allow(dead_code)]` 隐藏死代码 — 2个文件全量放行 | 移除文件级注解; 删除5个死函数; 11个结构体添加精确`#[allow(dead_code)]` | 2026-03-29 | R26 |
| HI-375 | `infra` | 3个Rust命令文件 | 硬编码macOS项目路径 — 非标准安装位置或Linux部署必崩 | `get_base_dir()`/`get_default_workspace_path()`/`get_unix_openclaw_paths()` 优先读 `OPENCLAW_PROJECT_DIR` env var | 2026-03-29 | R26 |
| HI-350 | `security` | `xianyu_live.py` | 闲鱼app-key硬编码在源码中 | `os.getenv("XIANYU_APP_KEY", "默认值")` 外部化 | 2026-03-29 | R26 |
| HI-284 | `backend` | `task_graph.py`+`_ai.py`+`x_platform.py`+`utils.py` | emit_flow 3处重复try/except fallback stub(18行×3)+utils.py自导入Bug | 删除3个stub改为直接import; 修复utils.py自引用; 合并分散的import | 2026-03-29 | R26 |
| HI-283 | `frontend` | 8个TSX/TS文件 | 前端残留英文注释/UI文案(11处) | 注释→中文; "sent"→"已发送"; "Command Palette"→"命令面板"; console.error→中文 | 2026-03-29 | R26 |
| HI-280 | `infra` | `scripts/newsyslog.openclaw.conf` | macOS LaunchAgent日志无轮转 — 无限增长吃磁盘 | newsyslog配置: 5日志×50MB×5归档×gzip(≤250MB) | 2026-03-29 | R26 |
| HI-380 | `frontend` | 8个TSX/TS文件 | 14个 `any` 类型使用 — 绕过TypeScript类型检查，可能隐藏运行时错误 | 替换为 `Record<string, unknown>` + 专用接口(PlatformEngagement/TopPost/AnalyticsData); 移除1个未使用导入 | 2026-03-29 | R25 |
| HI-379 | `frontend` | 6个Rust命令文件 | 7处安全隐患: URL编码多字节字符错误+token生成仅用时间戳+2个重复函数+3处 `.unwrap()` 可能panic | `urlencoding_encode` 改用 `.bytes()`; `generate_token` 读 `/dev/urandom`; 提取共享函数; `.unwrap()` → 安全替代 | 2026-03-29 | R25 |
| HI-378 | `infra` | `.gitignore` + Git索引 | 9101个运行时/构建文件被git跟踪(node_modules 6139+dist 2896+.openclaw ~60+其他) | `git rm --cached -r` 移除全部 + .gitignore新增15+规则防止重新加入 | 2026-03-29 | R25 |
| HI-374 | `backend` | 7个router文件 | 24个API端点无try/except — 原始Python异常直接泄露给API客户端 | 提取共享safe_error()到error_utils.py+7个router全量覆盖try/except | 2026-03-29 | R24审计修复 |
| HI-373 | `backend` | `bot/config.py` | SF Key轮转函数(get_siliconflow_key/update_key_balance/mark_key_exhausted)无线程锁 — asyncio事件循环+BackgroundScheduler线程竞态 | 添加threading.Lock()保护3个函数+get_total_balance | 2026-03-29 | R24审计修复 |
| HI-372 | `backend` | `x_platform.py`, `xhs_platform.py` | 6个async def函数内同步调用worker_fn() — 浏览器自动化(5-30s)冻结事件循环 | 包装为await asyncio.to_thread(worker_fn, ...) | 2026-03-29 | R24审计修复 |
| HI-371 | `backend` | 6个文件 | 6处硬编码User-Agent字符串版本不一致(Chrome 131 vs 133) | 提取到src/constants.py(DEFAULT_USER_AGENT+XIANYU_USER_AGENT)+6文件引用常量 | 2026-03-29 | R24审计修复 |
| HI-370 | `backend` | `executor.py`, `omega.yaml` | Twilio demo URL用HTTP不安全+omega.yaml 4段死配置(evolution/task_routing/social_times/life)未被代码消费 | Twilio URL改HTTPS+env var可配置; yaml 4段注释掉并标注原因 | 2026-03-29 | R24审计修复 |
| HI-369 | `backend` | 15个文件 | 33个无占位符f-string(f"text"应为"text") — 微浪费性能+代码规范问题 | Python 3.12 AST精确检测+列偏移定位修复(跨15文件) | 2026-03-29 | R23清理 |
| HI-368 | `infra` | 全项目 | 19个幽灵.pyc(源文件已删除)+5个空目录+deploy_bundle_final(4文件)被git跟踪 | 删除.pyc+删除空目录+git rm deploy_bundle_final+.gitignore补充 | 2026-03-29 | R23清理 |
| HI-367 | `backend` | `bot/globals.py` → `bot/config.py` | 循环依赖中心: globals↔history_store/context_manager/shared_memory互引(延迟import绕行) | 提取纯配置到config.py(107行)+6个consumer切换import路径+globals.py re-export向后兼容 | 2026-03-29 | HI-359修复 |
| HI-366 | `backend` | 7个文件 | 9个未使用import(auto_trader/freqtrade_bridge/trading_journal/context_manager/shared_memory/_helpers/cmd_analysis_mixin)+5个死依赖 | 删除import+注释requirements.txt中fpdf2/pyautogui/pyobjc-core/pyobjc-framework-Quartz/pydantic-settings | 2026-03-29 | R22续审计 |
| HI-365 | `security` | `config/.env.example` | 3个真实密钥(2个Telegram Bot Token+1个Mem0 API Key)暴露在示例文件+重复MEM0_API_KEY定义+过期5-Bot .env.example | 替换为占位符+删除重复+删除过期文件 | 2026-03-29 | R22续审计 |
| HI-364 | `backend` | 8个文件 | 14个未定义名称+4个幻影导入: callback_mixin(5缺失import+ibkr幻影)/workflow_mixin(4缺失import)/notify_style(缺logging)/proactive_engine(admin_ids逻辑Bug+get_history_store幻影)/xianyu_agent(PriceAgent不存在)/x_platform(_fetch_via_tweepy不存在)/rpc(3幻影)/team(2幻影) | 恢复import+重定向幻影+创建PriceAgent类+实现_fetch_via_tweepy+修复admin_ids为ALLOWED_USER_IDS | 2026-03-29 | R22续审计 |
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
| 🔴 阻塞 | 0 | 20 | 20 |
| 🟠 重要 | 4 | 93 | 97 |
| 🟡 一般 | 6 | 110 | 116 |
| 🔵 低优先 | 1 | 32 | 33 |
| **合计** | **11** | **255** | **266** |

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
