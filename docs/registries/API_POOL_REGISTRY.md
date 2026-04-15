# API_POOL_REGISTRY — LLM API 号池注册表

> 最后更新: 2026-04-10
> 本文件记录所有 API 提供商、Key 状态、官方限制、模型可用性。修改 API Key 或新增提供商时必须同步更新。

---

## 号池总览

| # | 提供商 | 类型 | Key 数量 | 限制 | 环境变量 |
|---|--------|------|----------|------|----------|
| 1 | SiliconFlow | 免费无限 | 4 | 无 (免费模型) | `SILICONFLOW_KEYS` |
| 2 | SiliconFlow 付费 | 付费 (14元/条) | 10 | 未实名,禁Pro | `SILICONFLOW_PAID_KEYS` |
| 3 | iflow | 免费无限 | 1 | 无 (14个顶级模型) | `SILICONFLOW_UNLIMITED_KEY` |
| 4 | Groq | 免费 | 1 | 按模型不同 30-60RPM, 1000-14400RPD | `GROQ_API_KEY` |
| 5 | Cerebras | 免费 | 1 | 30RPM, 当前接入 `gpt-oss-120b` / `llama3.1-8b` | `CEREBRAS_API_KEY` |
| 6 | Gemini (Google AI Studio) | 免费 | 1 | 2.5/3.x 系动态 RPM/RPD, 1M上下文 | `GEMINI_API_KEY` |
| 7 | OpenRouter | 免费 | 1 | :free模型 20RPM, 50-1000RPD | `OPENROUTER_API_KEY` |
| 8 | Mistral | 免费 | 1 | 低RPM, 数据用于训练 | `MISTRAL_API_KEY` |
| 9 | Cohere | 免费 | 1 | 1000次/月, 20RPM | `COHERE_API_KEY` |
| 10 | NVIDIA NIM | 信用额度 | 1 | ~60RPM, 额度用完停用 | `NVIDIA_NIM_API_KEY` |
| 11 | GPT_API_Free | 免费 | 1 | 5-200次/天 (按模型) | `GPT_API_FREE_KEY` |
| 12 | Claude 代理 | 付费 | 1 | 仅 `/claude` 显式调用，不再走 XAPI | `CLAUDE_API_KEY` |
| 13 | g4f 本地 | 免费 | 1 | 无 (本地代理) | `G4F_API_KEY` |
| 14 | Kiro Gateway | 免费 | 1 | ~5RPM (本地代理) | `KIRO_API_KEY` |
| 15 | Volcengine 火山 | 付费 | 1 | ~10RPM | `VOLCENGINE_API_KEY` |
| 16 | Zhipu 智谱 | 付费 | 1 | OCR专用 | `ZHIPU_API_KEY` |
| 17 | Sambanova | 免费 | 1 | ~10RPM (DeepSeek-R1) | `SAMBANOVA_API_KEY` |
| 18 | GitHub Models | 免费 | 1 | ~15RPM | `GITHUB_MODELS_TOKEN` |

## 非 LLM API

| # | 提供商 | 用途 | 限制 | 环境变量 |
|---|--------|------|------|----------|
| 19 | fal.ai | 图像/视频生成 | 按额度 | `FAL_KEY` |
| 20 | Deepgram | 语音转文字 | 按额度 | `DEEPGRAM_API_KEY` |
| 21 | Mem0 Cloud | 云端记忆 | 按额度 | `MEM0_API_KEY` |
| 22 | Kling AI | 视频生成 | 按额度 | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` |
| 23 | Manus AI | 联网搜索+编程 | 按额度 | `MANUS_API_KEY` |
| 24 | Vercel AI Gateway | AI网关 | 按额度 | `VERCEL_AI_KEY` |
| 25 | HuggingFace | 模型部署 | 免费额度 | `HUGGINGFACE_TOKEN` |
| 26 | SerpApi | 搜索引擎 | 250次/月, 50次/小时 | `SERPAPI_KEY` |
| 27 | Brave Search | 网页搜索 | 50QPS | `BRAVE_SEARCH_API_KEY` |
| 28 | CloudConvert | 文件格式转换 | 按额度 | `CLOUDCONVERT_API_KEY`（当前仅登记，主代码尚未接入） |
| 29 | Tavily | AI搜索 | 免费1000次/月 | `TAVILY_API_KEY` |
| 30 | 闲鱼 AI 客服 | 闲鱼专用LLM | 按额度 | `XIANYU_LLM_API_KEY` + `XIANYU_LLM_BASE_URL` + `XIANYU_LLM_MODEL` |
| 31 | Langfuse | LLM观测/追踪 | 免费额度 | `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_HOST` |
| 32 | 微信通知 | 微信消息推送 | 无 | `WECHAT_NOTIFY_ENABLED` |

---

## 详细限制 (基于官方文档)

### Groq — 极速推理

| 模型 | RPM | RPD | TPM | TPD | 上下文 |
|------|-----|-----|-----|-----|--------|
| `llama-3.3-70b-versatile` | 30 | 1,000 | 12,000 | 100,000 | 131K |
| `moonshotai/kimi-k2-instruct` | 60 | 1,000 | 10,000 | 300,000 | 262K |
| `openai/gpt-oss-120b` | 30 | 1,000 | 8,000 | 200,000 | 131K |
| `qwen/qwen3-32b` | 60 | 1,000 | 6,000 | 500,000 | 131K |
| `llama-3.1-8b-instant` | 30 | 14,400 | 6,000 | 500,000 | 131K |

### Gemini — Google AI Studio

| 模型 | 状态 | 上下文 | 输出 | 备注 |
|------|------|--------|------|------|
| `gemini-2.5-pro` | 稳定 | 1M | 65K | 最强, RPM低 |
| `gemini-2.5-flash` | 稳定 | 1M | 65K | 主力 |
| `gemini-2.5-flash-lite` | 稳定 | 1M | 65K | 轻量 |
| `gemini-3-flash-preview` | 预览 | 1M | 65K | 最新, 速率更严 |
| `gemini-2.0-flash` | **已从项目主链移除** | 1M | 8K | 官方已废弃 |

### Cerebras — 免费高速推理

- 当前项目重新启用 `gpt-oss-120b` 与 `llama3.1-8b`
- 官方免费层按模型 30RPM，适合作为高速开放模型补位
- 不参与 Claude 专用兜底链

### OpenRouter — 免费模型

- 无充值: 20RPM, **50RPD**
- 有充值 (≥$1): 20RPM, **1000RPD**
- 免费模型以 `:free` 后缀标识
- 项目中定位为后位免费兜底，不承担主链流量

### SiliconFlow 付费Key — 特别注意

- **10条Key, 每条14元余额, 全部未实名**
- **禁止调用含 "Pro" 的模型** → HTTP 403, 可能导致key报废
- 免费模型 (Qwen3-235B, GLM-4-32B) 不扣余额
- DeepSeek-R1 (非Pro) ~175次/key, DeepSeek-V3 ~1000次/key

### GPT_API_Free — 模型分级限制

| 模型组 | 日限制 |
|--------|--------|
| gpt-5/4o/4.1 系 | 5次/天 |
| deepseek-r1/v3 系 | 30次/天|
| gpt-4o-mini/3.5/nano 系 | 200次/天 |

### 当前项目主链与降级口径

- 主链优先: `SiliconFlow` → `iflow` → `Groq` → `Gemini 2.5/3.x`
- 中位补位: `Cerebras` → `OpenRouter free` → `NVIDIA NIM` → `Volcengine`
- 后位兜底: `Mistral` → `Cohere` → `GPT_API_Free` → `g4f`
- `Claude API` 仅保留给 `/claude` 显式调用，不再允许走 `XAPI/9w7` 空余额线路

---

## LiteLLM Router 模型强度排名 (节选)

| 分数 | 模型 | 提供商 |
|------|------|--------|
| 98 | gemini-2.5-pro | Google |
| 97 | gemini-2.5-flash | Google |
| 95 | claude-sonnet-4 / gemini-3-flash-preview | Kiro / Google |
| 94 | kimi-k2-instruct | Groq / iflow |
| 93 | DeepSeek-R1 | 多源 |
| 92 | o4-mini / Qwen3-235B | GitHub / SiliconFlow |
| 90 | Hermes-3-405B / DeepSeek-V3 | OpenRouter / SiliconFlow |

完整排名见 `src/litellm_router.py:MODEL_RANKING`。

---

## 配置文件位置

| 文件 | 用途 |
|------|------|
| `packages/clawbot/config/.env` | 所有 API Key 主配置 |
| `packages/clawbot/src/litellm_router.py` | LiteLLM Router 注册 + 模型排名 |
| `packages/clawbot/src/bot/globals.py` | Key 加载 + 余额管理 |
| `packages/clawbot/config/omega.yaml` | OMEGA 成本控制 + 模型路由映射 |
| `packages/clawbot/src/core/cost_control.py` | 日预算 + 成本跟踪 |
