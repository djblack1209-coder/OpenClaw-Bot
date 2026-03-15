# Bot Model Audit (2026-03-06)

## Scope

- Workspace: `~/Desktop/OpenClaw Bot/clawbot`
- Bots audited: `qwen235b`, `gptoss`, `claude_sonnet`, `claude_haiku`, `deepseek_v3`, `claude_opus`
- Methods:
  - Telegram `getMe` identity check for each configured token
  - Backend `/models` and minimal completion smoke tests
  - Runtime log validation (`com-clawbot-agent.stderr.log`)

## Current mapping and health

1) `qwen235b`
- Telegram: `@carven_Qwen235B_Bot`
- Model: `qwen-3-235b`
- Backend: g4f (`http://127.0.0.1:18891/v1`)
- Status: OK (works via `OperaAria` provider)

2) `gptoss`
- Telegram: `@carven_GPTOSS120B_Bot`
- Model: `gpt-oss-120b`
- Backend: g4f (`http://127.0.0.1:18891/v1`)
- Status: OK (works via `OperaAria` provider)

3) `claude_sonnet`
- Telegram: `@carven_ClaudeSonnet_Bot`
- Model: `claude-sonnet-4.5`
- Backend: Kiro (`http://127.0.0.1:18793/v1`)
- Status: OK

4) `claude_haiku`
- Telegram: `@carven_ClaudeHaiku_Bot`
- Model: `claude-haiku-4.5`
- Backend: Kiro (`http://127.0.0.1:18793/v1`)
- Status: OK

5) `deepseek_v3`
- Telegram: `@carven_DeepSeekV3_Bot`
- Model: `deepseek-3.2`
- Backend: Kiro (`http://127.0.0.1:18793/v1`)
- Status: OK

6) `claude_opus`
- Telegram: `@carven_ClaudeOpus_Bot`
- Model: `claude-opus-4-6`
- Backend: g4f (`http://127.0.0.1:18891/v1`, provider priority: `OperaAria`)
- Status: OK (smoke test returned exact `OK` on `claude-opus-4-6`)

## Drift found and fixed

- Fixed Telegram username drift in `clawbot/config/.env` (all six now match actual `@carven_*` usernames).
- Updated default usernames in `clawbot/multi_main.py` to match current Telegram identities.
- Fixed model labeling drift in `clawbot/config/bot_profiles.py`:
  - `Claude Sonnet 4.5`
  - `Claude Haiku 4.5`
- Updated g4f fallback priority in `clawbot/src/bot/api_mixin.py`:
  - Same-model + `OperaAria` first
  - Avoid unnecessary cross-model fallback (`qwen/gpt-oss` -> `aria`) unless needed
- Moved `deepseek_v3` from paid SiliconFlow route to free Kiro route (`deepseek-3.2`) in `clawbot/multi_main.py`.
- Moved `claude_opus` from failing Claude proxy route to g4f route in `clawbot/multi_main.py`.
- Added Opus-specific same-model fallback chain in `clawbot/src/bot/api_mixin.py` (`OperaAria` first, no cross-family fallback).
- Added Chinese text command aliases in `clawbot/src/bot/message_mixin.py` as Telegram-safe fallback for command localization.

## Free API options (verified references)

1) Groq (OpenAI-compatible)
- Docs: `https://console.groq.com/docs/rate-limits`
- Docs: `https://console.groq.com/docs/models`
- Free plan exists with per-model RPM/RPD/TPM limits.
- Includes `openai/gpt-oss-120b` and `qwen/qwen3-32b`.

2) OpenRouter free models
- Docs: `https://openrouter.ai/docs/faq`
- Free model variant supported (`:free`) with low rate limits.
- Suitable as backup/free router, not ideal for high-volume production without paid credits.

3) Cloudflare Workers AI
- Docs: `https://developers.cloudflare.com/workers-ai/platform/pricing/`
- Free allocation: `10,000 Neurons/day`.
- Supports multiple open models including GPT-OSS and Qwen families.

4) DeepSeek official API
- Docs: `https://api-docs.deepseek.com/quick_start/pricing`
- Official DeepSeek API is paid (no always-free production tier documented).

5) Anthropic official pricing (Claude API)
- Docs: `https://docs.anthropic.com/en/docs/about-claude/pricing`
- Claude API is paid; no always-free Opus API tier documented.

## Recommendation for Bot strategy

- Keep current six Telegram bots and current model alignment.
- Keep `claude_opus` on g4f `OperaAria` as primary free lane for now, and monitor provider stability daily.
- Keep a paid Opus-capable route as cold standby for production-critical workloads where determinism/SLAs are required.
