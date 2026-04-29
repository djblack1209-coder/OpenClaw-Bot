# 官方文档优先协议 (DOCS-FIRST PROTOCOL)

> 最后更新: 2026-04-01
> 本文件从 AGENTS.md §12 外移，AI 仅在触发条件命中时按需加载

---

## 强制触发条件

遇到以下任何情形，**必须**先执行文档拉取，否则禁止进入阶段 4（执行开发）：

| 触发场景 | 必须拉取 | 原因 |
|----------|----------|------|
| 修改 LiteLLM 路由 / 新增 LLM Provider | LiteLLM 路由文档 | Provider 参数和模型名频繁变更 |
| 修改 Telegram Bot 消息发送 / 键盘 / 回调 | PTB 最新 API 参考 | v20+ 与旧版 API 差异巨大 |
| 修改 FastAPI 路由 / 中间件 / 依赖注入 | FastAPI 对应功能页 | 版本迁移后行为有细微变化 |
| 修改 Tauri 命令 / 权限 / 进程间通信 | Tauri v2 对应页面 | v1→v2 API 已破坏性重写 |
| 新增 / 修改 CrewAI Agent 或 Task | CrewAI 对应文档 | Agent/Task 构造器参数频繁迭代 |
| 使用 browser-use 或 crawl4ai | 对应 GitHub README | 两个库均在快速迭代，API 变动频繁 |
| 修改 Redis 缓存 / 持久化配置 | Redis 命令文档 | 不同版本命令行为有差异 |
| 修改 Docker Compose 资源限制 / 健康检查 | Compose 规范文档 | healthcheck / deploy 字段版本敏感 |
| 修改 pytest fixture / 异步测试 | pytest 文档 | asyncio 模式在新版本有破坏性变更 |
| 修改 mem0 记忆读写 / 初始化 | mem0 官方文档 | Cloud 模式与本地模式 API 签名不同 (HI-219) |
| 修改 httpx AsyncClient 生命周期 | httpx 文档 | 不关闭会泄漏 TCP 连接 (HI-159/160) |
| 修改 APScheduler 调度器配置 | APScheduler 文档 | BackgroundScheduler 线程安全陷阱 (HI-373) |
| 使用任何 **本项目未曾用过的第三方库** | 该库官方文档首页 + Changelog | 防止用错 API、引入废弃用法 |

---

## 技术栈权威文档 URL 速查表

### Python 后端核心

| 技术 | 项目版本 | 官方文档地址 | 重点关注页面 |
|------|---------|-------------|-------------|
| **Python 3.12** | 3.12 | https://docs.python.org/3.12/ | `asyncio` / `datetime` / `typing` |
| **FastAPI** | >=0.115.0 | https://fastapi.tiangolo.com/ | Dependency Injection / Middleware / Exception Handlers |
| **LiteLLM** | >=1.70.0 | https://docs.litellm.ai/docs/ | Router / Provider Keys / Streaming |
| **LiteLLM Providers** | — | https://docs.litellm.ai/docs/providers | 各 Provider 模型名和参数格式 |
| **python-telegram-bot (PTB)** | ~=22.5 | https://docs.python-telegram-bot.org/en/v22.5/ | Application / Message / InlineKeyboard |
| **Pydantic v2** | ~=2.7.0 | https://docs.pydantic.dev/latest/ | Model / Validator / Field |
| **httpx** | ~=0.28.1 | https://www.python-httpx.org/ | AsyncClient 生命周期 / Timeout 配置 |
| **APScheduler** | >=3.10.0 | https://apscheduler.readthedocs.io/en/3.x/ | BackgroundScheduler 线程安全 |
| **Redis (Python)** | — | https://redis-py.readthedocs.io/en/stable/ | Connection Pool / Pipeline |
| **aiosqlite** | — | https://aiosqlite.omnilib.dev/en/stable/ | 异步连接 / 上下文管理器 |

### AI / Agent 框架

| 技术 | 项目版本 | 官方文档地址 | 重点关注页面 |
|------|---------|-------------|-------------|
| **CrewAI** | >=0.80.0 | https://docs.crewai.com/ | Agent / Task / Crew 构造器参数 |
| **browser-use** | >=0.2.0 | https://github.com/browser-use/browser-use#readme | 安装方式 + API 接口签名 |
| **crawl4ai** | >=0.6.0 | https://crawl4ai.com/mkdocs/ | AsyncWebCrawler / CrawlResult |
| **mem0** | >=0.1.30 | https://docs.mem0.ai/ | Memory / Client 初始化 / Cloud vs 本地模式差异 |
| **instructor** | >=1.7.0 | https://python.useinstructor.com/ | 结构化 LLM 输出 / Pydantic 集成 |

### 桌面端

| 技术 | 项目版本 | 官方文档地址 | 重点关注页面 |
|------|---------|-------------|-------------|
| **Tauri v2** | v2 | https://v2.tauri.app/ | Commands / Events / Permissions |
| **React 19** | 19 | https://react.dev/reference/react | Hooks / Suspense / Server Components |
| **Vite** | — | https://vitejs.dev/guide/ | 构建配置 / 环境变量 |

### 工程 / 部署

| 技术 | 官方文档地址 | 重点关注页面 |
|------|-------------|-------------|
| **Docker Compose v2** | https://docs.docker.com/compose/compose-file/ | `healthcheck` / `deploy.resources` |
| **pytest** | https://docs.pytest.org/en/stable/ | `asyncio_mode` / Fixtures |
| **pytest-asyncio** | https://pytest-asyncio.readthedocs.io/en/latest/ | `asyncio_mode=auto` |

### API 提供商

| 提供商 | 文档地址 | 重点关注 |
|--------|---------|---------|
| **SiliconFlow** | https://docs.siliconflow.cn/cn/api-reference/ | 模型列表 + Rate Limits |
| **Groq** | https://console.groq.com/docs/models | 模型名 + Context Length |
| **Gemini** | https://ai.google.dev/gemini-api/docs/models | 当前可用模型列表 |
| **OpenRouter** | https://openrouter.ai/docs | 路由参数 + 模型别名 |
| **Anthropic** | https://docs.anthropic.com/en/api/ | 模型名 + Tool Use |
| **IBKR TWS API** | https://ibkr.info/article/4416 | Order 类型 + 合约规范 |

---

## 文档拉取 SOP

```
Step 1: 识别触发技术 → 对照触发条件表
Step 2: 查 DEPENDENCY_MAP.md 确认项目版本
Step 3: 精准定位文档页面（不拉整站）
Step 4: 执行拉取（Context7 > WebFetch > GitHub搜索）
Step 5: 验证拉取结果（三种工具均失败 → 降级策略）
Step 6: 提取关键信息并与现有代码比对
Step 7: 代码注释中声明参考文档版本
Step 8: 以文档为准编写代码
```

### 多技术栈同时触发时的预算

| 同时触发数 | 策略 |
|-----------|------|
| 1 个 | 正常拉取 |
| 2-3 个 | 每个只拉最相关的 1 个页面 |
| 4+ 个 | 按优先级排序，只拉前 3 个 |

**优先级:** 幻觉高风险项 > 新库 > 有破坏性变更历史的库 > API 稳定的成熟库

---

## 幻觉高风险清单

| 风险点 | 幻觉类型 | 防御措施 | HI-ID |
|--------|---------|---------|-------|
| LiteLLM 模型名称 | 用了不存在的模型名 | 每次必查 Provider 文档 | HI-382 |
| PTB `Application.builder()` | 混用 v13 和 v20 API | 确认 PTB 版本后再写 | — |
| Tauri v2 `invoke` 权限 | 忘记声明权限 | 必查权限文档 | HI-335 |
| CrewAI `Agent` 构造器 | 传入已重命名参数 | 每次必查文档 | — |
| `asyncio` Python 3.12 | 误用废弃 `get_event_loop()` | 必查文档 | HI-267 |
| mem0 Cloud vs 本地 | `add()` 签名不同 | 确认使用模式 | HI-219 |
| httpx `AsyncClient` | 不 `aclose()` 泄漏连接 | 用 `async with` | HI-159/160 |
| APScheduler 线程安全 | 回调线程与 asyncio 竞态 | 共享状态加锁 | HI-373 |
| `subprocess` 调用 | `shell=True` 命令注入 | `shlex.split` + `shell=False` | HI-146/228/355 |

---

## 免责情形（不强制拉取）

- 仅修改中文注释 / 日志文本
- 修改配置文件中的数值
- 修改已有函数的业务逻辑（无新库调用）
- 修改文档
- 运行测试 / 语法检查

---

## 文档与代码不符时

| 情形 | 处理 |
|------|------|
| 旧 API 但仍兼容 | 登记 HEALTH.md (TECH_DEBT 🟡)，继续 |
| 已废弃 API 有风险 | 登记 HEALTH.md (TECH_DEBT 🟠)，建议修复 |
| API 已不存在/参数改名 | 登记 HEALTH.md (BUG 🔴)，必须修复 |

## 文档拉取失败

1. 换工具重试 (Context7 → WebFetch → GitHub)
2. 三种均失败 → 告知用户，基于训练数据继续，代码注释标注 `⚠️ 文档拉取失败`
3. 登记 HEALTH.md (TECH_DEBT 🟡)
