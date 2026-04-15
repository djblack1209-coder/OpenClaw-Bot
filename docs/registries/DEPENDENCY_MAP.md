# OpenClaw Bot — 依赖清单

> 最后更新: 2026-04-16 | 新增 lib-pybroker (共 80+ 个 Python 包)

## 搬运的高星项目 (38 个, 累计 ~473k Stars)

| 包 | Stars | 用途 | 文件 | 版本 |
|----|-------|------|------|------|
| crawl4ai | 62.4k | 购物比价引擎 | shopping/crawl4ai_engine.py | >=0.6.0 |
| RestrictedPython | 1.2k | 代码沙箱安全执行 | tools/code_tool.py | >=8.0 |
| jieba | 34.8k | 中文分词+意图识别 | core/intent_parser.py | >=0.42.1 |
| loguru | 23.7k | 全局结构化日志 | log_config.py | >=0.7.0 |
| plotly | 18.4k | K线图/饼图/瀑布图 | charts.py | >=6.0.0 |
| Apprise | 16.1k | 100+渠道通知 | notifications.py | >=1.9.0 |
| openpyxl | 12k | Excel 导出 | tools/export_service.py | >=3.1.0 |
| instructor | 10k | 结构化 LLM 输出 | structured_llm.py | >=1.7.0 |
| edge-tts | 10.3k | 零成本语音合成 | tts_engine.py | >=6.0.0 |
| Phoenix OTEL | 9k | LLM 可观测性 | observability.py | >=0.1.0 |
| vectorbt | 6.9k | 向量化策略回测 | modules/investment/backtester_vbt.py | >=0.26.0 |
| tenacity | 6k | 指数退避真重试 | core/self_heal.py | >=9.0.0 |
| pandas-ta | 5k | 标准技术指标 | strategy_engine.py | >=0.3.14b1 |
| quantstats | 4.8k | 回测报告+VaR/CVaR风控 | backtester_vbt.py, risk_var.py | >=0.0.62 |
| qrcode | 4.9k | 二维码生成 | tools/qr_service.py | >=7.0 |
| **PyBroker** | **3.3k** | **Numba加速回测+Bootstrap验证** | **modules/investment/backtester_pybroker.py** | **>=1.2.12** |
| diskcache | 2.8k | LLM 响应缓存 | llm_cache.py | >=5.6.0 |
| fpdf2 | 1.5k | PDF 报告 | tools/pdf_report.py | ==2.7.9 | ⚠️ 已注释 (HI-366) |
| stamina | 1.4k | 声明式重试 | resilience.py | >=2.0.0 |
| kaleido | 1.2k | Plotly 静态导出 | charts.py | >=0.2.0 |
| mistletoe | 1k | Telegram MD 渲染 | telegram_markdown.py | >=1.4.0 |
| PyrateLimiter | 485 | API 令牌桶限流 | resilience.py | >=3.0.0 |
| feedparser | 9.8k | RSS/Atom 解析 | news_fetcher.py | >=6.0.0 |
| snownlp | 6k | 中文情感分析 | social_tools.py | >=0.12.3 |
| textblob | 9k | 英文情感分析 | social_tools.py | >=0.18.0 |
| PyPortfolioOpt | 4.6k | 投资组合有效前沿优化 | rebalancer.py | >=1.5.0 |
| exchange-calendars | 4.1k | 全球交易所日历 (50+) | auto_trader.py | >=4.5.0 |
| alpaca-py | 1k | Alpaca 券商 SDK | alpaca_bridge.py | >=0.30.0 |
| composio-core | 20k | 250+ 外部服务 SDK (可选) | integrations/composio_bridge.py | >=0.7.0 |
| tvscreener | — | TradingView 股票筛选 API | universe.py | >=0.5.0 |
| price-parser | 4.2k | 智能价格提取 (全球货币) | shopping/price_engine.py | >=0.3.0 |
| tweepy | 10.6k | Twitter/X 官方 SDK | execution/social/x_platform.py | >=4.14.0 |
| dateparser | 2.5k | 自然语言时间解析 (13种语言) | execution/life_automation.py | >=1.2.0 |
| humanize | 2.9k | 自然语言时间/大小/数字格式化 | notify_style.py | >=4.9.0 |


## 原有核心依赖

| 包 | 用途 | 版本 |
|----|------|------|
| python-telegram-bot | Telegram Bot API | ~=22.5 |
| litellm | 统一 LLM 路由 | >=1.70.0 |
| mem0ai | AI 记忆层 | >=0.1.30 |
| browser-use | AI 浏览器代理 | >=0.2.0 |
| langfuse | LLM 观测平台 | >=2.0.0 |
| crewai | 多 Agent 协作 | >=0.80.0 |
| fastapi | 内控 API | >=0.115.0 |
| httpx | HTTP 客户端 | ~=0.28.1 |
| yfinance | 美股数据 | ~=1.1.0 |
| akshare | A股数据 | >=1.15.0 |
| ccxt | 加密货币 108+ 交易所 | >=4.4.0 |
| DrissionPage | 反检测浏览器 | >=4.1.0 |
| apscheduler | 定时任务 | >=3.10.0 |
| pandas / numpy / ta | 数据分析+技术指标 | ~=2.3.3 / ~=2.0.2 / ~=0.11.0 |
| optuna | 超参数优化 | >=4.0.0 |
| python-dotenv | 环境变量加载 (.env) | ~=1.2.1 |
| beautifulsoup4 | HTML 解析 | ~=4.14.3 |
| requests | HTTP 客户端 (同步) | ~=2.32.0 |
| flask | 部署服务器 (deployer/) | >=3.0.0 |
| aiohttp | 异步 HTTP (evolution/) | >=3.9.0 |
| json-repair | JSON 容错解析 (LLM 输出修复) | ~=0.30.0 |
| pydantic-settings | 配置管理 (类型校验+env) | ~=2.7.0 |
| websockets | 闲鱼 WebSocket 实时聊天 | ~=13.0 |
| openai | OpenAI SDK (闲鱼/Agent) | >=1.68.2 |
| ib_async | IBKR 券商对接 (ib_insync 社区接力 fork) | >=2.1.0 |
| tavily-python | AI 搜索引擎 SDK | >=0.5.0 |
| smolagents | 轻量 Agent 框架 (HuggingFace) | >=1.0.0 |
| docling | 文档理解引擎 (PDF/DOCX→MD) | >=2.0.0 |
| pybreaker | 工业级熔断器 (self_heal.py) | >=1.4.0 |

## Python 版本约束
- 当前: **Python 3.12** (venv: `.venv312`)
- 注意: `fpdf2` 锁定 `==2.7.9`
- 注意: `pandas-ta` 在 PyPI 上无法安装 (需 pip install from git)

## R8 新增/修正 (2026-03-27)

| 包 | 版本 | 用途 | 来源 |
|---|---|---|---|
| `playwright` | `>=1.40.0` | 浏览器自动化 (browser-use 底层依赖) | R1 审计新增 |
| `uvicorn[standard]` | `~=0.32.0` | ASGI 服务器 | requirements.txt 已有但注册表漏登 |
| `pyautogui` | `>=0.9.54` | macOS 桌面控制 | requirements.txt 已有但注册表漏登 |
| `pyobjc-core` | `>=10.0` | macOS Quartz 底层 | requirements.txt 已有但注册表漏登 |
| `arize-phoenix-otel` | `>=0.1.0` | Phoenix OTEL 客户端 | requirements.txt 已有但注册表漏登 |
| `openinference-instrumentation-litellm` | `>=0.1.0` | LiteLLM OTEL 插桩 | requirements.txt 已有但注册表漏登 |
| `pytest` / `pytest-asyncio` / `pytest-cov` | 多版本 | 测试框架 | requirements.txt 已有但注册表漏登 |

**已移除**: `tiktoken` — 注册表曾列出但 requirements.txt 未包含，代码中也未使用 (P5审计已从搬运表中替换为 RestrictedPython)
- 最低支持: Python 3.10 (`docling>=2.0.0` 要求)
