# OpenClaw Bot 全面优化实施计划

> 最后更新: 2026-03-27

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用成熟开源方案替换自研60分模块，保留独特壁垒（AI团队投票、人格系统），将体验从"能用"提升到"好用"。

**Architecture:** 6大改造模块并行推进：One-API网关替换、mem0内存深度集成、execution_hub拆分+browser-use集成、Telegram FSM重构、freqtrade交易引擎搬运、桌面端UI充实。每个模块独立可测试，不互相阻塞。

**Tech Stack:** Python 3.12, One-API (Go), mem0 + Chroma, browser-use, python-telegram-bot ConversationHandler, freqtrade IStrategy, React + shadcn/ui + Tremor

---

## 改造总览

| 模块 | 删除代码量 | 新增/改造代码量 | 净效果 |
|------|-----------|---------------|--------|
| One-API网关替换 | ~600行 (free_api_pool部分 + llm_router.py + api_mixin部分) | ~150行 (One-API配置 + 适配层) | -450行 |
| mem0内存集成 | ~1200行 (shared_memory向量搜索 + smart_memory全部) | ~200行 (mem0配置 + 适配层) | -1000行 |
| execution_hub拆分 | 3789行单文件 | ~3200行(18个模块) | 结构优化，可维护性大幅提升 |
| browser-use深度集成 | ~200行 (Chrome JS注入 + 旧browser_agent) | ~300行 (browser-use深度封装) | 可靠性提升 |
| Telegram FSM | ~100行 (死代码清理) | ~500行 (FSM + onboarding) | 体验质变 |
| freqtrade搬运 | ~3100行 (strategy_engine + backtester + protections + auto_trader执行部分 + trading_system) | ~800行 (freqtrade适配层 + AI信号提供者) | -2300行 |

**总计：净减少 ~3750行代码，同时功能和可靠性大幅提升。**

---

## Task 1: One-API 网关替换

**目标：** 用 One-API (31k星) 替换自研LLM路由的底层通道管理，保留上层自适应路由。

**Files:**
- Delete: `packages/clawbot/src/llm_router.py` (174行，完全重复)
- Modify: `packages/clawbot/src/free_api_pool.py` (935行 → ~400行)
- Modify: `packages/clawbot/src/bot/api_mixin.py` (539行 → ~350行)
- Create: `packages/clawbot/src/oneapi_client.py` (~80行)
- Create: `docker-compose.oneapi.yml` (~30行)
- Keep: `packages/clawbot/kiro-gateway/` (完整保留，注册为One-API上游通道)

### 关键决策

kiro-gateway 不是通用网关，是 Kiro IDE 凭证代理（免费Claude）。One-API 无法替代它。正确做法：
1. 部署 One-API 作为统一入口
2. 把 kiro-gateway 注册为 One-API 的一个 channel
3. 把 SiliconFlow/Groq/Cerebras/OpenRouter 等全部注册为 One-API channels
4. bot 代码只调 One-API 一个端点

### 保留的独特逻辑（One-API 没有的）

- `MODEL_RANKING` + `get_model_score()` — 40+模型质量评分
- `AdaptiveRouter` — 任务感知路由 + 自学习 + explain_route()
- `_call_claude_api()` — Claude tool-use 迭代循环
- `_call_api()` — 速率限制、token预算、质量门控
- `_call_api_stream()` — 流式 + 优雅降级

- [ ] **Step 1: 部署 One-API**

创建 `docker-compose.oneapi.yml`:
```yaml
version: '3'
services:
  one-api:
    image: justsong/one-api:latest
    container_name: openclaw-oneapi
    restart: always
    ports:
      - "3000:3000"
    volumes:
      - ./data/oneapi:/data
    environment:
      - SQL_DSN=file:/data/one-api.db
      - INITIAL_ROOT_TOKEN=$ONEAPI_ADMIN_KEY
```

- [ ] **Step 2: 启动 One-API 并配置 channels**

```bash
cd /Users/blackdj/Desktop/OpenClaw\ Bot
docker compose -f docker-compose.oneapi.yml up -d
```

通过 One-API 管理界面 (http://localhost:3000) 添加 channels:
- Channel 1: Kiro Gateway → http://host.docker.internal:8889/v1 (优先级1)
- Channel 2: SiliconFlow → https://api.siliconflow.cn/v1 (优先级2)
- Channel 3: Groq → https://api.groq.com/openai/v1 (优先级3)
- Channel 4: Cerebras → https://api.cerebras.ai/v1 (优先级4)
- Channel 5: OpenRouter → https://openrouter.ai/api/v1 (优先级5)
- Channel 6: Google AI Studio → https://generativelanguage.googleapis.com/v1beta (优先级6)

- [ ] **Step 3: 创建 One-API 客户端适配层**

创建 `packages/clawbot/src/oneapi_client.py`:
```python
"""One-API unified client — replaces direct provider calls."""
import httpx
import os
import logging

logger = logging.getLogger(__name__)

ONEAPI_BASE = os.getenv("ONEAPI_BASE_URL", "http://localhost:3000/v1")
ONEAPI_KEY = os.getenv("ONEAPI_API_KEY", "$ONEAPI_ADMIN_KEY")

async def call_oneapi(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    timeout: float = 120.0,
) -> dict | httpx.Response:
    """Single entry point for all LLM calls via One-API."""
    headers = {
        "Authorization": f"Bearer {ONEAPI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        if stream:
            return await client.post(
                f"{ONEAPI_BASE}/chat/completions",
                json=payload, headers=headers,
            )  # caller handles streaming
        resp = await client.post(
            f"{ONEAPI_BASE}/chat/completions",
            json=payload, headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def call_oneapi_stream(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
):
    """Streaming variant — yields SSE chunks."""
    headers = {
        "Authorization": f"Bearer {ONEAPI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", f"{ONEAPI_BASE}/chat/completions",
            json=payload, headers=headers,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]
```

- [ ] **Step 4: 删除 llm_router.py**

```bash
rm packages/clawbot/src/llm_router.py
```
这是 free_api_pool.py 的不完整复制品，174行全部重复。

- [ ] **Step 5: 精简 free_api_pool.py**

删除以下部分（~535行）：
- `_load_default_sources()` 函数（~190行）— One-API 管理 channels
- `FreeAPIPool` 类中的路由方法：`get_best_source()`, `get_any_source()`, `_score_source()`, `_check_health()`, `_daily_reset()` — One-API 处理
- `FreeAPISource` 的 RPM/TPM/daily limit 跟踪字段和 `can_accept_request()` — One-API 处理

保留以下部分（~400行）：
- `MODEL_RANKING` dict + `get_model_score()`
- `BOT_MODEL_FAMILY` mapping
- `AdaptiveRouter` 类完整保留（任务感知路由、自学习、explain_route）
- 路由策略常量

`AdaptiveRouter.route()` 改为返回推荐的 model name（而不是 FreeAPISource），由 `oneapi_client.call_oneapi(model=...)` 执行实际调用。

- [ ] **Step 6: 精简 api_mixin.py**

删除以下方法（~190行）：
- `_call_siliconflow_api()` — 直接提供商调用，One-API 处理
- `_call_openai_compatible_api()` — 通用调用 + g4f fallback chains
- `_call_free_pool_or_g4f()` — 源选择 + fallback
- `_call_opus_smart()` 的大部分 — 多层 fallback chain
- `_G4F_FALLBACK` dict

保留以下方法（~350行）：
- `_call_api()` — 外层编排（速率限制、token预算、质量门控、历史管理、指标）
- `_call_claude_api()` — Claude tool-use 迭代循环（应用层逻辑，不是代理层）
- `_call_api_stream()` — 流式消费 + 优雅降级

新增 `_call_via_oneapi()` 方法替代所有删除的方法：
```python
async def _call_via_oneapi(self, messages, model=None, stream=False):
    """Route through One-API. Model selected by AdaptiveRouter."""
    if model is None:
        model = adaptive_router.route(task_type="general")
    from .oneapi_client import call_oneapi, call_oneapi_stream
    if stream:
        return call_oneapi_stream(messages, model=model)
    return await call_oneapi(messages, model=model)
```

- [ ] **Step 7: 更新 .env 配置**

在 `packages/clawbot/config/.env` 添加：
```
ONEAPI_BASE_URL=http://localhost:3000/v1
ONEAPI_API_KEY=$ONEAPI_ADMIN_KEY
```

- [ ] **Step 8: 验证**

```bash
# 启动 One-API
docker compose -f docker-compose.oneapi.yml up -d

# 测试连通性
curl http://localhost:3000/v1/models -H "Authorization: Bearer $ONEAPI_ADMIN_KEY"

# 运行现有测试
cd packages/clawbot && python -m pytest tests/ -x -v
```

---
