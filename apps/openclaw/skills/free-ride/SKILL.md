---
name: free-ride
description: "Free model fallback via OpenRouter. Use when: (1) primary API key is exhausted or rate-limited, (2) user wants to minimize costs, (3) background/low-priority tasks that don't need frontier models. Provides a ranked list of free models on OpenRouter sorted by capability."
---

# Free Ride — OpenRouter Free Model Fallback

Use OpenRouter's free model tier as a fallback when paid APIs are unavailable or for low-priority tasks.

## Setup

1. Get a free API key at https://openrouter.ai/keys
2. Add to your environment (already configured in `~/.openclaw/.env`):
   ```
   OPENROUTER_API_KEY=sk-or-v1-xxxxx
   ```
   Status: CONFIGURED

## Free Models (ranked by capability, March 2026)

| Model | Context | Speed | Best For |
|-------|---------|-------|----------|
| `deepseek/deepseek-chat:free` | 128k | Fast | General chat, Chinese |
| `google/gemma-3-27b-it:free` | 96k | Fast | Reasoning, multilingual |
| `mistralai/mistral-small-3.1-24b-instruct:free` | 96k | Fast | Code, instruction following |
| `qwen/qwen3-32b:free` | 40k | Medium | Chinese, general |
| `meta-llama/llama-4-scout:free` | 512k | Medium | Long context |
| `google/gemini-2.5-pro-exp-03-25:free` | 1M | Slow | Complex reasoning |

## OpenRouter Config for OpenClaw

Add as a provider in `openclaw.json` (manual edit recommended):

```json
{
  "models": {
    "providers": {
      "openrouter_free": {
        "baseUrl": "https://openrouter.ai/api/v1",
        "apiKey": "YOUR_OPENROUTER_KEY",
        "api": "openai-completions",
        "models": [
          {
            "id": "deepseek/deepseek-chat:free",
            "name": "DeepSeek Chat (Free)",
            "api": "openai-completions",
            "reasoning": false,
            "input": ["text"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": 131072,
            "maxTokens": 8192
          }
        ]
      }
    }
  }
}
```

## Usage Strategy

- Add `openrouter_free/deepseek-chat:free` as a fallback in agent model config
- Use for: background cron tasks, routine scans, simple classification
- Don't use for: complex reasoning, code generation, production-critical tasks
- Rate limits apply per model — spread load across multiple free models

## Warning

Do NOT let OpenClaw auto-install this skill's config changes. Edit `openclaw.json` manually or use a coding agent to avoid breaking your existing provider setup.
