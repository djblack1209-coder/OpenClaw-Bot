# Kiro Gateway 文档集

> 合并自原 034-kiro-gateway-architecture.md + 035-kiro-gateway-agents.md + 036-kiro-gateway-contributing.md + 037-kiro-gateway-tests.md + 038-kiro-gateway-contributors.md + 039-kiro-gateway-cla.md

---

## 一、架构设计

# Architectural Overview: Kiro Gateway

## 1. System Purpose and Goals

The project is a high-level proxy gateway implementing the **"Adapter"** structural design pattern.

The main goal of the system is to provide transparent compatibility between multiple heterogeneous interfaces:

### Supported API Formats

| API | Endpoints | Status |
|-----|-----------|--------|
| **OpenAI** | `/v1/models`, `/v1/chat/completions` | ✅ Supported |
| **Anthropic** | `/v1/messages` | ✅ Supported |

### Architectural Model

```
┌─────────────────────────────────────────────────────────────────┐
│                          Clients                                │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI SDK/Tools   │       │ Anthropic SDK/Tools │         │
│  │  (Cursor, Cline,    │       │ (Claude Code,       │         │
│  │   Continue, etc.)   │       │  Anthropic SDK)     │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Kiro Gateway                               │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI Adapter     │       │  Anthropic Adapter  │         │
│  │  /v1/chat/...       │       │  /v1/messages       │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
│             └──────────────┬───────────────┘                    │
│                            ▼                                    │
│             ┌─────────────────────────────┐                     │
│             │      Core Layer             │                     │
│             │  (Shared conversion logic)  │                     │
│             └──────────────┬──────────────┘                     │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Kiro API                                 │
│              (AWS CodeWhisperer Backend)                        │
└─────────────────────────────────────────────────────────────────┘
```

The system acts as a "translator", allowing the use of any tools, libraries, and IDE plugins developed for OpenAI and Anthropic ecosystems with Claude models through the Kiro API.

**Both APIs work simultaneously** on the same server without any configuration switching.

## 2. Project Structure

The project is organized as a modular Python package `kiro/`:

```
kiro-gateway/
├── main.py                    # Entry point, FastAPI application creation
├── requirements.txt           # Python dependencies
├── .env.example               # Environment configuration example
│
├── kiro/              # Main package
│   ├── __init__.py            # Package exports, version
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # SHARED LAYER - Reused by all APIs
│   │   # ═══════════════════════════════════════════════════════
│   ├── config.py              # Configuration and constants
│   ├── auth.py                # KiroAuthManager - token management
│   ├── cache.py               # ModelInfoCache - model cache
│   ├── http_client.py         # HTTP client with retry logic
│   ├── parsers.py             # AWS SSE stream parsers
│   ├── utils.py               # Helper utilities
│   ├── tokenizer.py           # Token counting (tiktoken)
│   ├── debug_logger.py        # Debug request logging
│   ├── exceptions.py          # Exception handlers
│   ├── thinking_parser.py     # Thinking blocks parser
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # CORE LAYER - Shared core for all APIs
│   │   # ═══════════════════════════════════════════════════════
│   ├── converters_core.py     # Shared Kiro payload building logic
│   ├── streaming_core.py      # Shared Kiro stream parsing logic
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # OPENAI API LAYER
│   │   # ═══════════════════════════════════════════════════════
│   ├── models_openai.py       # Pydantic models for OpenAI API
│   ├── converters_openai.py   # OpenAI → Kiro adapter
│   ├── routes_openai.py       # FastAPI routes for OpenAI
│   ├── streaming_openai.py    # Kiro → OpenAI SSE formatter
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # ANTHROPIC API LAYER
│   │   # ═══════════════════════════════════════════════════════
│   ├── models_anthropic.py    # Pydantic models for Anthropic API
│   ├── converters_anthropic.py # Anthropic → Kiro adapter
│   ├── routes_anthropic.py    # FastAPI routes for Anthropic
│   └── streaming_anthropic.py # Kiro → Anthropic SSE formatter
│
├── tests/                     # Tests
│   ├── conftest.py            # Pytest fixtures
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
│
├── docs/                      # Documentation
│   ├── ru/                    # Russian version
│   └── en/                    # English version
│
└── debug_logs/                # Debug logs (generated when DEBUG_MODE=all or DEBUG_MODE=errors)
```

### Organization Principle: Shared Core + Thin Adapters

The architecture is built on the principle of **maximum code reuse**:

| Layer | Purpose | Files |
|-------|---------|-------|
| **Shared Layer** | Infrastructure independent of API format | `auth.py`, `http_client.py`, `cache.py`, `parsers.py`, `tokenizer.py` |
| **Core Layer** | Shared business logic for conversion | `converters_core.py`, `streaming_core.py` |
| **API Layer** | Thin adapters for specific formats | `*_openai.py`, `*_anthropic.py` |

## 3. Architectural Topology and Components

The system is built on the asynchronous `FastAPI` framework and uses an event-driven lifecycle management model (`Lifespan Events`).

### 3.1. Entry Point (`main.py`)

The `main.py` file is responsible for:

1. **Logging configuration** — Loguru setup with colored output
2. **Configuration validation** — `validate_configuration()` function checks:
   - Presence of `.env` file
   - Presence of credentials (REFRESH_TOKEN or KIRO_CREDS_FILE)
3. **Lifespan Manager** — creation and initialization of:
   - `KiroAuthManager` for token management
   - `ModelInfoCache` for model caching
4. **Error handler registration** — `validation_exception_handler` for 422 errors
5. **Route connection** — `app.include_router(router)`

### 3.2. Configuration Module (`kiro/config.py`)

Centralized storage of all settings:

| Parameter | Description | Default Value |
|-----------|-------------|---------------|
| `PROXY_API_KEY` | API key for proxy access | `changeme_proxy_secret` |
| `REFRESH_TOKEN` | Kiro refresh token | from `.env` |
| `PROFILE_ARN` | AWS CodeWhisperer profile ARN | from `.env` |
| `REGION` | AWS region | `us-east-1` |
| `KIRO_CREDS_FILE` | Path to JSON credentials file | from `.env` |
| `TOKEN_REFRESH_THRESHOLD` | Time before token refresh | 600 sec (10 min) |
| `MAX_RETRIES` | Max retry attempts | 3 |
| `BASE_RETRY_DELAY` | Base retry delay | 1.0 sec |
| `MODEL_CACHE_TTL` | Model cache TTL | 3600 sec (1 hour) |
| `DEFAULT_MAX_INPUT_TOKENS` | Default max input tokens | 200000 |
| `TOOL_DESCRIPTION_MAX_LENGTH` | Max tool description length | 10000 characters |
| `DEBUG_MODE` | Debug logging mode | `off` (off/errors/all) |
| `DEBUG_DIR` | Debug logs directory | `debug_logs` |
| `APP_VERSION` | Application version | `0.0.0` |

**Helper functions:**
- `get_kiro_refresh_url(region)` — URL for token refresh
- `get_kiro_api_host(region)` — main API host
- `get_kiro_q_host(region)` — Q API host
- `get_internal_model_id(external_model)` — model name conversion

### 3.3. Pydantic Models (`kiro/models_openai.py`)

#### Models for `/v1/models`

| Model | Description |
|-------|-------------|
| `OpenAIModel` | AI model description (id, object, created, owned_by) |
| `ModelList` | Model list for endpoint response |

#### Models for `/v1/chat/completions`

| Model | Description |
|-------|-------------|
| `ChatMessage` | Chat message (role, content, tool_calls, tool_call_id) |
| `ToolFunction` | Tool function description (name, description, parameters) |
| `Tool` | OpenAI format tool (type, function) |
| `ChatCompletionRequest` | Generation request (model, messages, stream, tools, ...) |

#### Response Models

| Model | Description |
|-------|-------------|
| `ChatCompletionChoice` | Single response variant |
| `ChatCompletionUsage` | Token information (prompt_tokens, completion_tokens, credits_used) |
| `ChatCompletionResponse` | Full response (non-streaming) |
| `ChatCompletionChunk` | Streaming chunk |
| `ChatCompletionChunkDelta` | Delta changes in chunk |
| `ChatCompletionChunkChoice` | Variant in streaming chunk |

### 3.4. State Management Layer

#### KiroAuthManager (`kiro/auth.py`)

**Role:** Stateful singleton encapsulating Kiro token management logic.

**Capabilities:**
- Loading credentials from `.env` or JSON file
- Support for `expiresAt` to check token expiration time
- Automatic token refresh 10 minutes before expiration
- Saving updated tokens back to JSON file
- Support for different AWS regions
- Unique fingerprint generation for User-Agent

**Concurrency Control:** Uses `asyncio.Lock` to protect against race conditions.

**Main methods:**
- `get_access_token()` — returns valid token, refreshing if necessary
- `force_refresh()` — forced token refresh (on 403)
- `is_token_expiring_soon()` — expiration time check

**Properties:**
- `profile_arn` — profile ARN
- `region` — AWS region
- `api_host` — API host for region
- `q_host` — Q API host for region
- `fingerprint` — unique machine fingerprint

```python
# Usage example
auth_manager = KiroAuthManager(
    refresh_token="your_token",
    region="us-east-1",
    creds_file="~/.aws/sso/cache/kiro-auth-token.json"
)
token = await auth_manager.get_access_token()
```

#### ModelInfoCache (`kiro/cache.py`)

**Role:** Thread-safe storage for model configurations.

**Population Strategy:**
- Lazy Loading via `/ListAvailableModels`
- Cache TTL: 1 hour
- Fallback to static model list

**Main methods:**
- `update(models_data)` — cache update
- `get(model_id)` — get model information
- `get_max_input_tokens(model_id)` — get token limit
- `is_empty()` / `is_stale()` — cache state check
- `get_all_model_ids()` — list of all model IDs

### 3.5. Helper Utilities (`kiro/utils.py`)

| Function | Description |
|----------|-------------|
| `get_machine_fingerprint()` | SHA256 hash of `{hostname}-{username}-kiro-gateway` |
| `get_kiro_headers(auth_manager, token)` | Form headers for Kiro API |
| `generate_completion_id()` | ID in format `chatcmpl-{uuid_hex}` |
| `generate_conversation_id()` | UUID for conversation |
| `generate_tool_call_id()` | ID in format `call_{uuid_hex[:8]}` |

### 3.6. Conversion Layer (`kiro/converters_openai.py`)

#### Message Conversion

OpenAI messages are transformed into Kiro conversationState:

1. **System prompt** — added to the first user message
2. **Message history** — fully passed in `history` array
3. **Adjacent message merging** — messages with the same role are merged
4. **Tool calls** — OpenAI tools format support
5. **Tool results** — correct transmission of tool call results

#### Long Tool Description Handling

**Problem:** Kiro API returns error 400 for too long descriptions in `toolSpecification.description`.

**Solution:** Tool Documentation Reference Pattern
- If `description ≤ TOOL_DESCRIPTION_MAX_LENGTH` → leave as is
- If `description > TOOL_DESCRIPTION_MAX_LENGTH`:
  * In `toolSpecification.description` → reference: `"[Full documentation in system prompt under '## Tool: {name}']"`
  * In system prompt, section `"## Tool: {name}"` with full description is added

**Function:** `process_tools_with_long_descriptions(tools)` → `(processed_tools, tool_documentation)`

#### Main Functions

| Function | Description |
|----------|-------------|
| `extract_text_content(content)` | Extract text from various formats |
| `merge_adjacent_messages(messages)` | Merge adjacent messages with same role |
| `build_kiro_history(messages, model_id)` | Build history array for Kiro |
| `build_kiro_payload(request_data, conversation_id, profile_arn)` | Full payload for request |

#### Model Mapping

External model names are converted to internal Kiro IDs:

| External Name | Internal Kiro ID |
|---------------|------------------|
| `claude-opus-4-5` | `claude-opus-4.5` |
| `claude-opus-4-5-20251101` | `claude-opus-4.5` |
| `claude-haiku-4-5` | `claude-haiku-4.5` |
| `claude-haiku-4.5` | `claude-haiku-4.5` (direct passthrough) |
| `claude-sonnet-4-5` | `CLAUDE_SONNET_4_5_20250929_V1_0` |
| `claude-sonnet-4-5-20250929` | `CLAUDE_SONNET_4_5_20250929_V1_0` |
| `claude-sonnet-4` | `CLAUDE_SONNET_4_20250514_V1_0` |
| `claude-sonnet-4-20250514` | `CLAUDE_SONNET_4_20250514_V1_0` |
| `claude-3-7-sonnet-20250219` | `CLAUDE_3_7_SONNET_20250219_V1_0` |
| `auto` | `claude-sonnet-4.5` (alias) |

### 3.7. Parsing Layer (`kiro/parsers.py`)

#### AwsEventStreamParser

Advanced AWS SSE format parser with support for:

- **Bracket counting** — correct parsing of nested JSON objects
- **Content deduplication** — filtering of duplicate events
- **Tool calls** — parsing of structured and bracket-style tool calls
- **Escape sequences** — decoding of `\n` and others

#### Event Types

| Event | Description |
|-------|-------------|
| `content` | Text content of the response |
| `tool_start` | Start of tool call (name, toolUseId) |
| `tool_input` | Continuation of input for tool call |
| `tool_stop` | End of tool call |
| `usage` | Credit consumption information |
| `context_usage` | Context usage percentage |

#### Helper Functions

| Function | Description |
|----------|-------------|
| `find_matching_brace(text, start_pos)` | Find closing brace with nesting support |
| `parse_bracket_tool_calls(response_text)` | Parse `[Called func with args: {...}]` |
| `deduplicate_tool_calls(tool_calls)` | Remove duplicate tool calls |

### 3.8. Streaming (`kiro/streaming_openai.py`)

#### stream_kiro_to_openai

Async generator for transforming Kiro stream to OpenAI format.

**Functionality:**
- Parse AWS SSE stream via `AwsEventStreamParser`
- Form OpenAI `chat.completion.chunk`
- Handle tool calls (structured and bracket-style)
- Calculate usage based on `contextUsagePercentage`
- Debug logging via `debug_logger`

#### collect_stream_response

Collects full response from streaming for non-streaming mode.

### 3.9. HTTP Client (`kiro/http_client.py`)

#### KiroHttpClient

Automatic error handling with exponential backoff:

| Error Code | Action |
|------------|--------|
| `403` | Token refresh via `force_refresh()` + retry |
| `429` | Exponential backoff: `BASE_RETRY_DELAY * (2 ** attempt)` |
| `5xx` | Exponential backoff (up to MAX_RETRIES attempts) |
| Timeout | Exponential backoff |

**Delay formula:** `1s, 2s, 4s` (with `BASE_RETRY_DELAY=1.0`)

**Methods:**
- `request_with_retry(method, url, json_data, stream)` — request with retry
- `close()` — close client

Supports async context manager (`async with`).

### 3.10. Routes (`kiro/routes_openai.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check (status, message, version) |
| `/health` | GET | Detailed health check (status, timestamp, version) |
| `/v1/models` | GET | List of available models (requires API key) |
| `/v1/chat/completions` | POST | Chat completions (requires API key) |

**Authentication:** Bearer token in `Authorization` header

### 3.11. Exception Handling (`kiro/exceptions.py`)

| Function | Description |
|----------|-------------|
| `sanitize_validation_errors(errors)` | Convert bytes to strings for JSON serialization |
| `validation_exception_handler(request, exc)` | Pydantic validation error handler (422) |

### 3.12. Debug Logging (`kiro/debug_logger.py`)

**Class:** `DebugLogger` (singleton)

**Activation:** `DEBUG_MODE=all` or `DEBUG_MODE=errors` in `.env`

**Methods:**
| Method | Description |
|--------|-------------|
| `prepare_new_request()` | Clear directory for new request |
| `log_request_body(body)` | Save incoming request |
| `log_kiro_request_body(body)` | Save request to Kiro API |
| `log_raw_chunk(chunk)` | Append raw chunk from Kiro |
| `log_modified_chunk(chunk)` | Append transformed chunk |

**Files in `debug_logs/`:**
- `request_body.json` — incoming request (OpenAI format)
- `kiro_request_body.json` — request to Kiro API
- `response_stream_raw.txt` — raw stream from Kiro
- `response_stream_modified.txt` — transformed stream (OpenAI format)

### 3.13. Tokenizer (`kiro/tokenizer.py`)

**Problem:** Kiro API does not return token counts directly. Instead, the API only provides `context_usage_percentage` — the percentage of model context usage.

**Solution:** Tokenizer module based on `tiktoken` (OpenAI's Rust library) for fast token counting.

**Features:**
- Uses `cl100k_base` encoding (GPT-4), close to Claude tokenization
- Correction factor `CLAUDE_CORRECTION_FACTOR = 1.15` for improved accuracy
- Lazy initialization for faster imports
- Fallback to rough estimation if tiktoken is unavailable

**Token calculation formula in response:**
```
total_tokens = context_usage_percentage × max_input_tokens  (from Kiro API)
completion_tokens = tiktoken(response)                       (our calculation)
prompt_tokens = total_tokens - completion_tokens             (subtraction)
```

**Main functions:**

| Function | Description |
|----------|-------------|
| `count_tokens(text)` | Count tokens in text |
| `count_message_tokens(messages)` | Count tokens in message list |
| `count_tools_tokens(tools)` | Count tokens in tool definitions |
| `estimate_request_tokens(messages, tools)` | Full request token estimation |

**Debug log:**
```
[Usage] claude-opus-4-5: prompt_tokens=142211 (subtraction), completion_tokens=769 (tiktoken), total_tokens=142980 (API Kiro)
```

**Accuracy:** ~97-99.7% compared to API data.

### 3.14. Kiro API Endpoints

All URLs are dynamically formed based on the region:

*   **Token Refresh:** `POST https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
*   **List Models:** `GET https://q.{region}.amazonaws.com/ListAvailableModels`
*   **Generate Response:** `POST https://codewhisperer.{region}.amazonaws.com/generateAssistantResponse`

## 4. Detailed Data Flow

### 4.1 Multi-API Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENTS                                │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI Client      │       │  Anthropic Client   │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              │ POST /v1/chat/completions    │ POST /v1/messages
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API LAYER                                  │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  routes_openai.py   │       │ routes_anthropic.py │         │
│  │  Security Gate      │       │ Security Gate       │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
│             │                              │                    │
│             ▼                              ▼                    │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │converters_openai.py │       │converters_anthropic │         │
│  │ Extract system      │       │ System already      │         │
│  │ from messages       │       │ separate in request │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              └──────────────┬───────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE LAYER                                 │
│             ┌─────────────────────────────┐                     │
│             │    converters_core.py       │                     │
│             │  build_kiro_payload()       │                     │
│             │  build_kiro_history()       │                     │
│             │  process_tools()            │                     │
│             └──────────────┬──────────────┘                     │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SHARED LAYER                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ KiroAuthManager │  │ KiroHttpClient  │  │  ModelInfoCache │ │
│  │   (auth.py)     │  │(http_client.py) │  │   (cache.py)    │ │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘ │
└───────────┼────────────────────┼────────────────────────────────┘
            │                    │
            │                    │ POST /generateAssistantResponse
            │                    ▼
            │         ┌─────────────────────────────────────┐
            │         │              Kiro API                   │
            │         └──────────────────┬──────────────────────┘
            │                            │
            │                            │ AWS SSE Stream
            │                            ▼
┌───────────┼────────────────────────────────────────────────────┐
│           │            CORE LAYER                              │
│           │  ┌─────────────────────────────┐                   │
│           │  │    streaming_core.py        │                   │
│           │  │  parse_kiro_stream()        │                   │
│           │  │  → KiroEvent objects        │                   │
│           │  └──────────────┬──────────────┘                   │
└────────────────────────────┼───────────────────────────────────┘
                             │
              ┌──────────────┴───────────────┐
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OUTPUT LAYER                               │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │streaming_openai.py  │       │streaming_anthropic  │         │
│  │ format_openai_sse() │       │format_anthropic_sse │         │
│  │                     │       │                     │         │
│  │ data: {...}         │       │ event: type         │         │
│  │ data: [DONE]        │       │ data: {...}         │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENTS                                │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI Client      │       │  Anthropic Client   │         │
│  └─────────────────────┘       └─────────────────────┘         │
└─────────────────────────────────┘
```

### 4.2 OpenAI API Flow

```
OpenAI Client
     │ POST /v1/chat/completions
     ▼
routes_openai.py ──► converters_openai.py ──► converters_core.py
     │                                              │
     │                                              ▼
     │                                        Kiro Payload
     │                                              │
     ▼                                              ▼
KiroAuthManager ──────────────────────────► KiroHttpClient
                                                   │
                                                   ▼
                                              Kiro API
                                                   │
                                                   ▼
streaming_core.py ◄─────────────────────── AWS SSE Stream
     │
     ▼
streaming_openai.py
     │
     ▼
OpenAI SSE Format ──────────────────────► OpenAI Client
```

### 4.3 Anthropic API Flow

```
Anthropic Client
     │ POST /v1/messages
     ▼
routes_anthropic.py ──► converters_anthropic.py ──► converters_core.py
     │                                                    │
     │                                                    ▼
     │                                              Kiro Payload
     │                                                    │
     ▼                                                    ▼
KiroAuthManager ──────────────────────────────────► KiroHttpClient
                                                         │
                                                         ▼
                                                    Kiro API
                                                         │
                                                         ▼
streaming_core.py ◄─────────────────────────────── AWS SSE Stream
     │
     ▼
streaming_anthropic.py
     │
     ▼
Anthropic SSE Format ──────────────────────────► Anthropic Client
```

## 5. Available Models

| Model | Description | Credits |
|-------|-------------|---------|
| `claude-opus-4-5` | Top-tier model | ~2.2 |
| `claude-opus-4-5-20251101` | Top-tier model (version) | ~2.2 |
| `claude-sonnet-4-5` | Enhanced model | ~1.3 |
| `claude-sonnet-4-5-20250929` | Enhanced model (version) | ~1.3 |
| `claude-sonnet-4` | Balanced model | ~1.3 |
| `claude-sonnet-4-20250514` | Balanced (version) | ~1.3 |
| `claude-haiku-4-5` | Fast model | ~0.4 |
| `claude-3-7-sonnet-20250219` | Legacy model | ~1.0 |

## 6. Configuration

### Environment Variables (.env)

```env
# Required
REFRESH_TOKEN="your_kiro_refresh_token"
PROXY_API_KEY="your_proxy_secret"

# Optional
PROFILE_ARN="arn:aws:codewhisperer:..."
KIRO_REGION="us-east-1"
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# Debug
DEBUG_MODE="off"  # off/errors/all
DEBUG_DIR="debug_logs"

# Limits
TOOL_DESCRIPTION_MAX_LENGTH="10000"
```

### JSON Credentials File (optional)

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "profileArn": "arn:aws:codewhisperer:us-east-1:...",
  "region": "us-east-1"
}
```

## 7. API Endpoints

### 7.1 Common Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Detailed health check |

### 7.2 OpenAI-compatible Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List of available models |
| `/v1/chat/completions` | POST | Chat completions (streaming/non-streaming) |

**Authentication:** `Authorization: Bearer {PROXY_API_KEY}`

### 7.3 Anthropic-compatible Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/messages` | POST | Messages API (streaming/non-streaming) |

**Authentication:** `x-api-key: {PROXY_API_KEY}` + `anthropic-version: 2023-06-01`

### 7.4 Format Comparison

| Aspect | OpenAI | Anthropic |
|--------|--------|-----------|
| System prompt | In `messages` with `role: "system"` | Separate `system` field |
| Content | String or array | Always array of content blocks |
| Stop reason | `finish_reason: "stop"` | `stop_reason: "end_turn"` |
| Usage | `prompt_tokens`, `completion_tokens` | `input_tokens`, `output_tokens` |
| Streaming | `data: {...}\n\n` + `data: [DONE]` | `event: type\ndata: {...}\n\n` |
| Tool format | `{type: "function", function: {...}}` | `{name: "...", input_schema: {...}}` |

## 8. Implementation Features

### Tool Calling

Support for OpenAI-compatible tools format:

```json
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get weather for a location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {"type": "string"}
        }
      }
    }
  }]
}
```

### Streaming

Full SSE streaming support with correct OpenAI format:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

data: [DONE]
```

### Debugging

When `DEBUG_MODE=all` or `DEBUG_MODE=errors`, all requests and responses are logged in `debug_logs/`:
- `request_body.json` — incoming request
- `kiro_request_body.json` — request to Kiro API
- `response_stream_raw.txt` — raw stream from Kiro
- `response_stream_modified.txt` — transformed stream

## 9. Extensibility

### Adding a New API Format

The modular architecture allows easy addition of support for other API formats. Thanks to the Core Layer, most of the logic is already implemented.

#### Steps to Add a New Format (e.g., Gemini)

1. **Create models** — `models_gemini.py`
   ```python
   class GeminiRequest(BaseModel):
       """Pydantic model for Gemini request."""
       contents: List[GeminiContent]
       ...
   ```

2. **Create conversion adapter** — `converters_gemini.py`
   ```python
   from kiro.converters_core import build_kiro_payload

   def gemini_to_kiro(request: GeminiRequest, ...) -> dict:
       """Converts Gemini request to Kiro payload."""
       # Extract data from Gemini format
       system_prompt = extract_system_instruction(request)
       messages = convert_gemini_contents(request.contents)
       tools = convert_gemini_tools(request.tools)

       # Use shared core
       return build_kiro_payload(
           messages=messages,
           system_prompt=system_prompt,
           tools=tools,
           ...
       )
   ```

3. **Create streaming formatter** — `streaming_gemini.py`
   ```python
   from kiro.streaming_core import parse_kiro_stream

   async def stream_to_gemini(response, ...) -> AsyncGenerator[str, None]:
       """Formats Kiro events to Gemini SSE."""
       async for event in parse_kiro_stream(response):
           yield format_gemini_chunk(event)
   ```

4. **Create routes** — `routes_gemini.py`
   ```python
   router = APIRouter()

   @router.post("/v1beta/models/{model}:generateContent")
   async def generate_content(request: GeminiRequest):
       ...
   ```

5. **Connect in main.py**
   ```python
   from kiro.routes_gemini import router as gemini_router
   app.include_router(gemini_router)
   ```

### What Gets Reused Automatically

When adding a new format, the following components work out of the box:

| Component | Functionality |
|-----------|---------------|
| `auth.py` | Kiro token management |
| `http_client.py` | HTTP with retry logic |
| `cache.py` | Model cache |
| `parsers.py` | AWS SSE parsing |
| `tokenizer.py` | Token counting |
| `converters_core.py` | Kiro payload building |
| `streaming_core.py` | Kiro stream parsing |

## 10. Dependencies

Main project dependencies (from `requirements.txt`):

| Package | Purpose |
|---------|---------|
| `fastapi` | Asynchronous web framework |
| `uvicorn` | ASGI server |
| `httpx` | Asynchronous HTTP client |
| `pydantic` | Data validation and models |
| `python-dotenv` | Environment variable loading |
| `loguru` | Advanced logging |
| `tiktoken` | Fast token counting |

---

## 二、AI Agent 工作指令


This document provides essential information for AI agents (Claude, GPT, etc.) working in the Kiro Gateway codebase.

## Project Philosophy

**Kiro Gateway is a transparent proxy with minimal, purposeful modifications.**

### Core Principles

1. **Transparency First**
   - The gateway preserves the user's original intent and request structure
   - Modifications are made only when necessary to work around Kiro API limitations or to add opt-in enhancements
   - We fix API quirks, not user decisions

2. **Minimal Intervention**
   - Changes to requests are surgical and well-justified
   - We add capabilities (like extended thinking) but never remove user content
   - Every modification must serve a clear purpose: fixing validation issues, adding optional features, or improving compatibility

3. **User Control**
   - All optional enhancements must be configurable
   - Users can disable features to get native Kiro API behavior
   - The gateway respects user choices about conversation structure and content

4. **Clear Boundaries**
   - ✅ **We fix**: API validation quirks, format incompatibilities, authentication flows
   - ✅ **We add (optionally)**: Enhanced features that Kiro API doesn't provide natively
   - ❌ **We don't modify**: User's conversation content, context decisions, message priorities
   - ❌ **We don't decide**: What messages to keep, what to trim, what's "important"

5. **Responsibility Separation**
   - Gateway handles API-level issues
   - Client handles content-level decisions
   - Model handles capacity limitations

6. **Systems Over Patches**
   - When solving a problem, we build systems that handle entire classes of issues, not one-off fixes
   - Even if a quick if-else would work, we invest time in creating proper abstractions and dedicated modules
   - Solutions should be easily extensible without modifying core logic
   - We prefer spending a few extra minutes on architecture that scales over quick hacks that accumulate technical debt
   - Every fix is an opportunity to create infrastructure that prevents similar problems in the future

7. **Paranoid Testing Philosophy**
   - Every commit must include tests - no exceptions
   - Tests exist to break code, not to confirm it works
   - Happy path alone is worthless - we test edge cases, error scenarios, boundary conditions, and malformed inputs
   - If you can't think of ways to break your code, you haven't thought hard enough
   - Two basic tests are not testing - comprehensive coverage means testing every logical branch and failure mode
   - Tests are both documentation and a safety net - they should clearly show what the code does and prevent regressions

8. **Code Quality Standards**
   - Comprehensive docstrings for all functions (Google style with Args/Returns/Raises)
   - Type hints are mandatory - every function parameter and return value must be typed
   - Logging at key decision points using loguru (INFO for business logic, DEBUG for technical details, ERROR for failures)
   - Never use bare `except:` or `except Exception:` - catch specific exceptions and add context
   - Proactive tech debt cleanup - if you see hardcoded values or duplicated code, extract it immediately (constants, functions, modules)
   - No placeholders - every function must be complete and production-ready when committed

9. **User Experience First**
   - Error messages must be actionable and user-friendly, not technical jargon
   - When something fails, explain what went wrong and how to fix it
   - Configuration should be intuitive with sensible defaults
   - Debug logging exists to help users troubleshoot, not just for developers
   - Documentation is part of the feature - if users can't figure it out, it doesn't work
   - Every error should guide the user toward a solution, not leave them confused

### About "Improperly formed request" Errors

**Important**: Kiro API's "Improperly formed request" error is notoriously vague due to poor documentation from Amazon. This single error message can indicate many different validation issues:

- Message structure problems (wrong role order, missing required fields)
- Tool definition issues (invalid schemas, name length violations)
- Content format problems (malformed JSON, unsupported content types)
- Authentication or permission issues
- Undocumented API constraints

When debugging this error, systematic testing is required to identify the actual cause. The gateway fixes known validation quirks, but new edge cases may emerge as Kiro API evolves.

## Project Overview

**Kiro Gateway** is a Python FastAPI proxy server that provides OpenAI-compatible and Anthropic-compatible APIs for Kiro (Amazon Q Developer / AWS CodeWhisperer). It translates requests between different API formats and handles authentication, streaming, model resolution, and error handling.

- **Language**: Python 3.10+
- **Framework**: FastAPI with uvicorn
- **License**: AGPL-3.0
- **Main Entry Point**: `main.py`
- **Package**: `kiro/` directory

## Essential Commands

### Running the Server

```bash
# Default (host: 0.0.0.0, port: 8000)
python main.py

# Custom port
python main.py --port 9000

# Custom host and port
python main.py --host 127.0.0.1 --port 9000

# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_auth_manager.py -v

# Run specific test
pytest tests/unit/test_auth_manager.py::TestKiroAuthManagerInitialization::test_initialization_stores_credentials -v

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Stop on first failure
pytest -x

# Show local variables on errors
pytest -l

# Run with coverage
pip install pytest-cov
pytest --cov=kiro --cov-report=html
```

### Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Main dependencies:
# - fastapi
# - uvicorn[standard]
# - httpx
# - loguru
# - requests
# - python-dotenv
# - tiktoken
# - pytest
# - pytest-asyncio
# - hypothesis
```

### Docker (Containerization)

```bash
# Build Docker image
docker build -t kiro-gateway .

# Run with Docker (using environment variables)
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="your-secret-key" \
  -e REFRESH_TOKEN="your-refresh-token" \
  --name kiro-gateway \
  kiro-gateway

# Run with docker-compose (recommended)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Run with custom .env file
docker-compose --env-file .env.production up -d

# Mount credentials file (Kiro IDE)
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway

# Mount kiro-cli database
docker run -d \
  -p 8000:8000 \
  -v ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli:ro \
  -e KIRO_CLI_DB_FILE=/home/kiro/.local/share/kiro-cli/data.sqlite3 \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway
```

**Docker Features:**
- Single-stage optimized build
- Non-root user (`kiro`) for security
- Health check endpoint monitoring (`/health`)
- Volume mounts for credentials and debug logs
- Automatic restart on failure
- Support for all 4 authentication methods
- Resource limits (optional in docker-compose.yml)

**CI/CD Integration:**
- GitHub Actions workflow (`.github/workflows/docker.yml`)
- Automated testing before Docker build
- Docker image testing (health checks)
- Automatic push to GitHub Container Registry (ghcr.io) on main branch
- Coverage report generation

## Project Structure

```
kiro-gateway/
├── main.py                          # Application entry point
├── kiro/                            # Main package
│   ├── __init__.py                  # Package exports
│   ├── config.py                    # Configuration and constants
│   ├── auth.py                      # Authentication manager
│   ├── cache.py                     # Model metadata cache
│   ├── model_resolver.py            # Dynamic model resolution
│   ├── http_client.py               # HTTP client with retry logic
│   ├── routes_openai.py             # OpenAI API endpoints
│   ├── routes_anthropic.py          # Anthropic API endpoints
│   ├── converters_core.py           # Shared conversion logic
│   ├── converters_openai.py         # OpenAI format converters
│   ├── converters_anthropic.py      # Anthropic format converters
│   ├── streaming_core.py            # Shared streaming logic
│   ├── streaming_openai.py          # OpenAI streaming
│   ├── streaming_anthropic.py       # Anthropic streaming
│   ├── parsers.py                   # AWS SSE stream parsers
│   ├── thinking_parser.py           # Thinking block parser (FSM)
│   ├── models_openai.py             # OpenAI Pydantic models
│   ├── models_anthropic.py          # Anthropic Pydantic models
│   ├── network_errors.py            # Network error classification
│   ├── exceptions.py                # Exception handlers
│   ├── debug_logger.py              # Debug logging system
│   ├── debug_middleware.py          # Debug middleware
│   ├── tokenizer.py                 # Token counting (tiktoken)
│   └── utils.py                     # Helper utilities
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
├── .env.example                     # Environment configuration template
├── requirements.txt                 # Python dependencies
└── pytest.ini                       # Pytest configuration
```

## Code Architecture

### Modular Design

The codebase follows a layered architecture:

1. **Routes Layer** (`routes_*.py`): FastAPI endpoints, authentication, request validation
2. **Converters Layer** (`converters_*.py`): Format translation (OpenAI/Anthropic → Kiro)
3. **Streaming Layer** (`streaming_*.py`): SSE stream processing (Kiro → OpenAI/Anthropic)
4. **Core Services**: Auth, HTTP client, model resolution, caching
5. **Parsers**: AWS event stream parsing, thinking block extraction
6. **Models**: Pydantic models for validation

### Key Components

#### Authentication (`auth.py`)

- **KiroAuthManager**: Manages token lifecycle
- Supports multiple auth methods:
  - JSON credentials file (Kiro IDE)
  - Environment variables (refresh token)
  - SQLite database (kiro-cli)
  - AWS SSO OIDC (Builder ID, Enterprise)
- Auto-detects auth type based on credentials
- Thread-safe token refresh with asyncio.Lock
- Automatic refresh before expiration

#### Model Resolution (`model_resolver.py`)

4-layer resolution pipeline:
1. **Normalize Name**: Convert client formats to Kiro format (dashes→dots, strip dates)
2. **Check Dynamic Cache**: Models from /ListAvailableModels API
3. **Check Hidden Models**: Manual config for undocumented models
4. **Pass-through**: Unknown models sent to Kiro (let Kiro decide)

Key principle: **We are a gateway, not a gatekeeper**. Kiro API is the final arbiter.

#### HTTP Client (`http_client.py`)

- **KiroHttpClient**: HTTP client with automatic retry logic
- Handles errors:
  - 403: Automatic token refresh and retry
  - 429: Exponential backoff
  - 5xx: Exponential backoff
  - Timeouts: Exponential backoff
- Supports per-request clients (for streaming) and shared clients (for connection pooling)
- Network error classification with user-friendly messages

#### Streaming (`streaming_*.py`)

- Parses AWS event stream format
- Converts to OpenAI or Anthropic SSE format
- Handles thinking blocks (extended thinking mode)
- First token timeout with retry logic
- Tool call parsing and deduplication

#### Converters (`converters_*.py`)

- **Core Layer** (`converters_core.py`): Shared logic for both APIs
  - UnifiedMessage format
  - Tool processing and sanitization
  - Message merging
  - Kiro payload building
- **OpenAI Adapter** (`converters_openai.py`): OpenAI → Kiro
- **Anthropic Adapter** (`converters_anthropic.py`): Anthropic → Kiro

## Code Conventions

### Naming

- **Functions/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`

### Type Hints

Always use type hints:

```python
def extract_text_content(content: Any) -> str:
    """Extract text from various content formats."""
    pass

async def refresh_token(self) -> str:
    """Refresh access token."""
    pass
```

### Docstrings

Use Google-style docstrings with Args/Returns sections:

```python
def normalize_model_name(name: str) -> str:
    """
    Normalize client model name to Kiro format.

    Transformations applied:
    1. claude-haiku-4-5 → claude-haiku-4.5 (dash to dot for minor version)
    2. claude-haiku-4-5-20251001 → claude-haiku-4.5 (strip date suffix)

    Args:
        name: External model name from client

    Returns:
        Normalized model name in Kiro format

    Examples:
        >>> normalize_model_name("claude-haiku-4-5-20251001")
        'claude-haiku-4.5'
    """
    pass
```

### Logging

Use loguru for all logging:

```python
from loguru import logger

logger.info("Server starting...")
logger.warning("Token expiring soon")
logger.error(f"Failed to refresh token: {e}")
logger.debug(f"Request payload: {payload}")
```

Log levels:
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages
- `WARNING`: Warning messages (non-critical issues)
- `ERROR`: Error messages (failures)

### Error Handling

```python
from fastapi import HTTPException

# For API errors
raise HTTPException(status_code=401, detail="Invalid API Key")

# For internal errors with logging
try:
    result = await some_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Async/Await

All I/O operations are async:

```python
async def fetch_models(self) -> List[str]:
    """Fetch available models from Kiro API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

## Testing Philosophy

### Complete Network Isolation

**Critical**: All tests MUST be completely isolated from the network.

- Global fixture `block_all_network_calls` in `tests/conftest.py` blocks all httpx requests
- Any attempt to make real network calls will fail the test
- All external services are mocked

### Test Structure

Tests follow the **Arrange-Act-Assert** pattern:

```python
@pytest.mark.asyncio
async def test_token_refresh_success(mock_env_vars, mock_kiro_token_response):
    """
    Test successful token refresh.

    What it does: Verifies that KiroAuthManager correctly refreshes tokens
    Purpose: Ensure token lifecycle management works correctly
    """
    # Arrange
    auth_manager = KiroAuthManager()
    mock_response = mock_kiro_token_response(expires_in=3600)

    # Act
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response
        token = await auth_manager.get_valid_token()

    # Assert
    assert token == mock_response["accessToken"]
    assert auth_manager._access_token == token
```

### Test Organization

- **Unit tests** (`tests/unit/`): Test individual functions/classes in isolation
- **Integration tests** (`tests/integration/`): Test component interactions
- Test classes: `Test*Success`, `Test*Errors`, `Test*EdgeCases`
- Test names: `test_<what_it_does>_<expected_result>`

### Running Tests

Always run tests after making changes:

```bash
# Quick check
pytest tests/unit/test_<module>.py -v

# Full suite
pytest -v

# With coverage
pytest --cov=kiro --cov-report=html
```

## Configuration

### Environment Variables

Configuration is loaded from `.env` file (see `.env.example`):

```bash
# Required
PROXY_API_KEY="my-super-secret-password-123"

# Authentication (choose one method)
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"  # JSON file
REFRESH_TOKEN="your_refresh_token"                        # Direct token
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3" # SQLite DB

# Optional
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
VPN_PROXY_URL="http://127.0.0.1:7890"  # For restricted networks

# Debug logging (off by default)
DEBUG_MODE="off"  # or "errors" or "all"
```

### Configuration Priority

1. CLI arguments: `python main.py --port 9000`
2. Environment variables: `SERVER_PORT=9000`
3. Default values: `8000`

## Important Patterns and Gotchas

### 1. Per-Request HTTP Clients for Streaming

**Critical**: Always use per-request clients for streaming to prevent CLOSE_WAIT leaks.

```python
# ✅ Correct: Per-request client for streaming
async with httpx.AsyncClient(timeout=timeout) as client:
    async with client.stream("POST", url, json=payload) as response:
        async for line in response.aiter_lines():
            yield line

# ❌ Wrong: Reusing shared client for streaming causes CLOSE_WAIT
```

### 2. Model Name Normalization

Model names are normalized before resolution:

```python
# Client sends: "claude-haiku-4-5-20251001"
# Normalized to: "claude-haiku-4.5"
# Sent to Kiro: "claude-haiku-4.5"
```

### 3. Tool Call Parsing

Kiro API may return tool calls in bracket format `[{...}]` instead of proper JSON. The parser handles this:

```python
# Kiro returns: "[{\"name\":\"get_weather\",\"arguments\":{...}}]"
# Parser extracts: [{"name": "get_weather", "arguments": {...}}]
```

### 4. Thinking Block Extraction

Extended thinking mode uses a finite state machine (FSM) to extract thinking blocks:

```python
# Input: "Let me think...<thinking>reasoning here</thinking>The answer is..."
# Extracted thinking: "reasoning here"
# Extracted content: "Let me think...The answer is..."
```

### 5. Network Error Classification

Network errors are classified into user-friendly categories:

```python
# httpx.ConnectTimeout → "Connection timeout"
# httpx.ReadTimeout → "Server response timeout"
# DNS errors → "DNS resolution failed"
```

### 6. Authentication Auto-Detection

Auth type is auto-detected based on credentials:

```python
# Has clientId/clientSecret → AWS SSO OIDC
# No clientId/clientSecret → Kiro Desktop Auth
```

### 7. Debug Logging Modes

Debug logging has three modes:

- `off`: Disabled (default, production)
- `errors`: Save logs only for failed requests (4xx, 5xx) - **recommended for troubleshooting**
- `all`: Save logs for every request (development)

Logs are saved to `debug_logs/` directory.

### 8. VPN/Proxy Support

For users in restricted networks (China, corporate):

```bash
VPN_PROXY_URL="http://127.0.0.1:7890"      # HTTP proxy
VPN_PROXY_URL="socks5://127.0.0.1:1080"    # SOCKS5 proxy
VPN_PROXY_URL="http://<user>:<password>@proxy:8080" # With auth
```

## Common Tasks

### Adding a New Endpoint

1. Define Pydantic models in `models_*.py`
2. Add route in `routes_*.py`
3. Add converter in `converters_*.py`
4. Add streaming logic in `streaming_*.py`
5. Write tests in `tests/unit/test_routes_*.py`

### Adding a New Model

Models are dynamically fetched from Kiro API. To add a hidden model:

```python
# In config.py
HIDDEN_MODELS = [
    "claude-new-model-1.0",
]
```

### Debugging Issues

1. Enable debug logging: `DEBUG_MODE="errors"` in `.env`
2. Check `debug_logs/` directory for request/response logs
3. Run tests: `pytest tests/unit/test_<module>.py -v`
4. Check application logs (loguru output)

### Making Changes

1. **Read before editing**: Always view files before modifying
2. **Follow existing patterns**: Check similar code for style
3. **Add tests**: Write tests for new functionality
4. **Run tests**: `pytest -v` before committing
5. **Check types**: Use type hints throughout
6. **Document**: Add docstrings with Args/Returns

## API Endpoints

### OpenAI-Compatible API

- `GET /`: Health check
- `GET /health`: Detailed health check
- `GET /v1/models`: List available models
- `POST /v1/chat/completions`: Chat completions (streaming and non-streaming)

### Anthropic-Compatible API

- `POST /v1/messages`: Messages API (streaming and non-streaming)

### Authentication

All endpoints require authentication:

```bash
# OpenAI format
Authorization: Bearer {PROXY_API_KEY}

# Anthropic format
x-api-key: {PROXY_API_KEY}
```

## Dependencies and Imports

### Core Dependencies

```python
# FastAPI
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader

# HTTP client
import httpx

# Logging
from loguru import logger

# Environment
from dotenv import load_dotenv
import os

# Type hints
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator

# Async
import asyncio

# Pydantic
from pydantic import BaseModel, Field, validator
```

### Internal Imports

```python
# Configuration
from kiro.config import PROXY_API_KEY, REGION, APP_VERSION

# Auth
from kiro.auth import KiroAuthManager, AuthType

# Models
from kiro.models_openai import ChatCompletionRequest, ChatMessage
from kiro.models_anthropic import AnthropicMessagesRequest

# Converters
from kiro.converters_openai import build_kiro_payload
from kiro.converters_anthropic import build_kiro_payload_anthropic

# Streaming
from kiro.streaming_openai import stream_kiro_to_openai
from kiro.streaming_anthropic import stream_kiro_to_anthropic

# HTTP client
from kiro.http_client import KiroHttpClient

# Model resolution
from kiro.model_resolver import ModelResolver, normalize_model_name
```

## Git Workflow

### Recent Changes

Check recent commits for context:

```bash
git log --oneline -20
```

Recent features:
- Network error classification with user-friendly messages
- Per-request clients for streaming (CLOSE_WAIT leak fix)
- Cursor flat format support
- Inverted model names support
- HTTP/SOCKS5 proxy support
- Enterprise Kiro IDE support
- AWS SSO OIDC authentication

### Making Commits

Follow existing commit message style:

```bash
# Format: <type>(<scope>): <description> (#issue)
# Types: feat, fix, docs, test, refactor, chore

git commit -m "feat(auth): add support for new auth method"
git commit -m "fix(streaming): handle empty chunks correctly"
git commit -m "docs: update configuration examples"
```

## Security Considerations

1. **Never log credentials**: Tokens, API keys, passwords
2. **Sanitize errors**: Don't expose internal details to clients
3. **Validate input**: Use Pydantic models for all requests
4. **Use HTTPS**: In production, always use HTTPS
5. **Rate limiting**: Consider adding rate limiting for production

## Performance Considerations

1. **Connection pooling**: Use shared httpx.AsyncClient for non-streaming requests
2. **Per-request clients**: Use per-request clients for streaming to prevent leaks
3. **Async everywhere**: All I/O operations are async
4. **Caching**: Model metadata is cached to reduce API calls
5. **Streaming**: Use streaming for large responses to reduce memory usage

## Troubleshooting

### Tests Failing

```bash
# Check if dependencies are installed
pip install -r requirements.txt

# Run specific test with verbose output
pytest tests/unit/test_<module>.py::test_<name> -v -s

# Check for network isolation violations
# All tests should pass without internet connection
```

### Server Not Starting

```bash
# Check if port is already in use
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# Use different port
python main.py --port 9000

# Check environment variables
cat .env
```

### Authentication Errors

```bash
# Check credentials file exists
ls -la ~/.aws/sso/cache/

# Check environment variables
echo $REFRESH_TOKEN
echo $KIRO_CREDS_FILE

# Enable debug logging
DEBUG_MODE="errors" python main.py
```

## Resources

- **README.md**: User-facing documentation
- **tests/README.md**: Testing documentation
- **.env.example**: Configuration template
- **GitHub Issues**: https://github.com/jwadow/kiro-gateway/issues

## Summary

Kiro Gateway is a well-architected Python FastAPI application with:

- ✅ Modular design with clear separation of concerns
- ✅ Comprehensive test suite with complete network isolation
- ✅ Type hints and docstrings throughout
- ✅ Async/await for all I/O operations
- ✅ Automatic retry logic and error handling
- ✅ Dynamic model resolution
- ✅ Multiple authentication methods
- ✅ Streaming support for both OpenAI and Anthropic APIs
- ✅ Debug logging system
- ✅ VPN/Proxy support for restricted networks

When working in this codebase:
1. **Read before editing** - Always view files first
2. **Follow patterns** - Check similar code for style
3. **Test everything** - Run `pytest -v` after changes
4. **Use type hints** - Always add type annotations
5. **Document changes** - Add docstrings with Args/Returns
6. **Isolate tests** - Never make real network calls in tests

---

## 三、贡献指南


Thanks for your interest in contributing!

## Philosophy

Kiro Gateway is a **transparent proxy** - we fix API-level issues while preserving user intent. When solving problems, we build systems that handle entire classes of issues, not one-off patches. We test paranoidly (happy path + edge cases + error scenarios), write clean code (type hints, docstrings, logging), and make errors actionable for users.

## Getting Started

1. Fork and clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure
4. Run tests: `pytest -v`

## Development Workflow

```bash
# Create a branch
git checkout -b fix/your-fix
# or
git checkout -b feat/your-feature

# Make changes and test
pytest -v

# Commit (Conventional Commits format)
git commit -m "fix(scope): description"

# Push and open PR
git push origin your-branch
```

## Standards

- **Tests required** - Every commit must include comprehensive tests
- **Type hints** - All functions must be typed
- **Docstrings** - Google style with Args/Returns/Raises
- **Logging** - Use loguru at key decision points
- **Error handling** - Catch specific exceptions, add context
- **No tech debt** - Clean up hardcoded values and duplication immediately

## Pull Requests

**Before submitting:**
- Tests pass (including edge cases)
- Code follows project style
- Error messages are user-friendly
- No placeholders or TODOs
- Changes are focused. Don't mix functional changes with mass formatting/whitespace fixes across many files

**PR should include:**
- Clear description of what and why
- Link to related issue
- Test coverage summary

**Keep it reviewable:**
- If fixing formatting, limit it to files you're actually changing
- Avoid auto-formatter changes across the entire codebase in the same PR as functional changes

## CLA

All contributors must sign the Contributor License Agreement (automated via bot).

## Questions?

- **Bug reports:** [Open an issue](https://github.com/jwadow/kiro-gateway/issues)
- **Feature ideas:** Discuss in an issue first
- **Questions:** [Start a discussion](https://github.com/jwadow/kiro-gateway/discussions)

## Recognition

Contributors are listed in [`CONTRIBUTORS.md`](CONTRIBUTORS.md).

---

**For detailed guidelines:** See [`AGENTS.md`](AGENTS.md)

---

## 四、测试文档


A comprehensive set of unit and integration tests for Kiro Gateway, providing full coverage of all system components.

## Testing Philosophy: Complete Network Isolation

**The key principle of this test suite is 100% isolation from real network requests.**

This is achieved through a global, automatically applied fixture `block_all_network_calls` in `tests/conftest.py`. It intercepts and blocks any attempts by `httpx.AsyncClient` to establish connections at the application level.

**Benefits:**
1.  **Reliability**: Tests don't depend on external API availability or network state.
2.  **Speed**: Absence of real network delays makes test execution instant.
3.  **Security**: Guarantees that test runs never use real credentials.

Any attempt to make an unauthorized network call will result in immediate test failure with an error, ensuring strict isolation control.

## Running Tests

### Installing Dependencies

```bash
# Main project dependencies
pip install -r requirements.txt

# Additional testing dependencies
pip install pytest pytest-asyncio hypothesis
```

### Running All Tests

```bash
# Run the entire test suite
pytest

# Run with verbose output
pytest -v

# Run with verbose output and coverage
pytest -v -s --tb=short

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Run a specific file
pytest tests/unit/test_auth_manager.py -v

# Run a specific test
pytest tests/unit/test_auth_manager.py::TestKiroAuthManagerInitialization::test_initialization_stores_credentials -v
```

### pytest Options

```bash
# Stop on first failure
pytest -x

# Show local variables on errors
pytest -l

# Run in parallel mode (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto
```

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures and utilities
├── unit/                            # Unit tests for individual components
│   ├── test_auth_manager.py        # KiroAuthManager tests
│   ├── test_cache.py               # ModelInfoCache tests (is_valid_model, add_hidden_model)
│   ├── test_config.py              # Configuration tests (SERVER_HOST, SERVER_PORT, LOG_LEVEL, etc.)
│   ├── test_converters_anthropic.py # Anthropic Messages API → Kiro converter tests
│   ├── test_converters_core.py     # Shared conversion logic tests (UnifiedMessage, merging, truncation recovery system prompt)
│   ├── test_converters_openai.py   # OpenAI Chat API → Kiro converter tests
│   ├── test_debug_logger.py        # DebugLogger tests (off/errors/all modes)
│   ├── test_debug_middleware.py    # DebugLoggerMiddleware tests (endpoint filtering, mode handling)
│   ├── test_exceptions.py          # Exception handlers tests (validation_exception_handler, sanitize_validation_errors)
│   ├── test_http_client.py         # KiroHttpClient tests
│   ├── test_kiro_errors.py         # Kiro API error enhancement tests (CONTENT_LENGTH_EXCEEDS_THRESHOLD, unknown errors)
│   ├── test_main_cli.py            # CLI argument parsing tests (--host, --port)
│   ├── test_model_resolver.py      # Dynamic Model Resolution System tests
│   ├── test_models_anthropic.py    # Anthropic Pydantic models tests (all content blocks, tools, streaming)
│   ├── test_models_openai.py       # OpenAI Pydantic models tests (messages, tools, responses, streaming)
│   ├── test_network_errors.py      # Network error handling tests
│   ├── test_parsers.py             # AwsEventStreamParser tests (JSON truncation diagnostics, truncation recovery integration)
│   ├── test_routes_anthropic.py    # Anthropic API endpoint tests (/v1/messages, truncation recovery message modification)
│   ├── test_routes_openai.py       # OpenAI API endpoint tests (/v1/chat/completions, truncation recovery message modification)
│   ├── test_streaming_anthropic.py # Anthropic streaming response tests
│   ├── test_streaming_core.py      # Shared streaming logic tests
│   ├── test_streaming_openai.py    # OpenAI streaming response tests
│   ├── test_thinking_parser.py     # ThinkingParser tests (FSM for thinking blocks)
│   ├── test_tokenizer.py           # Tokenizer tests (tiktoken)
│   ├── test_truncation_recovery.py # Truncation Recovery System tests (synthetic message generation)
│   ├── test_truncation_state.py    # Truncation state cache tests (save/retrieve, one-time retrieval, thread safety)
│   └── test_vpn_proxy.py           # VPN/Proxy configuration tests (environment variables, URL normalization, NO_PROXY)
├── integration/                     # Integration tests for full flow
│   └── test_full_flow.py           # End-to-end tests
└── README.md                        # This file
```

## Testing Philosophy

### Principles

1. **Isolation**: Each test is completely isolated from external services through mocks
2. **Detail**: Abundant print() for understanding test flow during debugging
3. **Coverage**: Tests cover not only happy path, but also edge cases and errors
4. **Security**: All tests use mock credentials, never real ones

### Test Structure (Arrange-Act-Assert)

Each test follows the pattern:
1. **Arrange** (Setup): Prepare mocks and data
2. **Act** (Action): Execute the tested action
3. **Assert** (Verify): Verify result with explicit comparison

### Test Types

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Verify component interactions
- **Security tests**: Verify security system
- **Edge case tests**: Paranoid edge case checks

## Adding New Tests

When adding new tests:

1. Follow existing class structure (`Test*Success`, `Test*Errors`, `Test*EdgeCases`)
2. Use descriptive names: `test_<what_it_does>_<expected_result>`
3. Add docstring with "What it does" and "Purpose"
4. Use print() for logging test steps

## Troubleshooting

### Tests fail with ImportError

```bash
# Make sure you're in project root
cd /path/to/kiro-gateway

# pytest.ini already contains pythonpath = .
# Just run pytest
pytest
```

### Tests pass locally but fail in CI

- Check dependency versions in requirements.txt
- Ensure all mocks correctly isolate external calls

### Async tests don't work

```bash
# Make sure pytest-asyncio is installed
pip install pytest-asyncio

# Check for @pytest.mark.asyncio decorator
```

## Coverage Metrics

To check code coverage:

```bash
# Install coverage
pip install pytest-cov

# Run with coverage report
pytest --cov=kiro --cov-report=html

# View report
open htmlcov/index.html  # macOS/Linux
start htmlcov/index.html  # Windows
```

## Contacts and Support

If you find bugs or have suggestions for test improvements, create an issue in the project repository.

---

## 五、贡献者


Thank you to all the contributors who have helped improve this project!

## Contributors

- [@Kartvya69](https://github.com/Kartvya69) — STREAMING_READ_TIMEOUT feature (#9)
- [@uratmangun](https://github.com/uratmangun) — Testing, debugging, and providing the fix for AWS SSO OIDC support (#12)
- [@JoeGrimes123](https://github.com/JoeGrimes123) — Suggesting the fake reasoning approach (#11)
- [@kilhyeonjun](https://github.com/kilhyeonjun) — SQLite credentials reload for containers (#22), thinking tags fix for toolResults (#23)
- [@cniu6](https://github.com/cniu6) — Image content block support inspiration (#26)
- [@somehow-paul](https://github.com/somehow-paul) — Enterprise Kiro IDE support (#45, #48), Cursor IDE compatibility design (#49)
- [@bhaskoro-muthohar](https://github.com/bhaskoro-muthohar) — Root cause analysis for MCP tool results (#46, #50) and message structure validation (#60)
- [@PAzter1101](https://github.com/PAzter1101) — Docker containerization with CI/CD (#55)
- [@Ry-DS](https://github.com/Ry-DS) — Images in tool results support for Anthropic MCP servers (#57)
- [@saaj](https://github.com/saaj) — Regional endpoint fix for eu-central-1 and other non-us-east-1 regions (#58)

---

## 六、CLA 协议


**Kiro Gateway**

Version 1.0 — Effective Date: December 2025

---

## Introduction

Thank you for your interest in contributing to **Kiro Gateway** (the "Project"), maintained by **Jwadow** (the "Maintainer"). This Contributor License Agreement ("Agreement") documents the rights granted by contributors to the Maintainer.

By submitting a Contribution to this Project, you accept and agree to the following terms and conditions for your present and future Contributions.

---

## 1. Definitions

**"You" (or "Your")** means the copyright owner or legal entity authorized by the copyright owner that is making this Agreement with the Maintainer.

**"Contribution"** means any original work of authorship, including any modifications or additions to an existing work, that is intentionally submitted by You to the Maintainer for inclusion in the Project. This includes any communication sent to the Project's repositories, issue trackers, mailing lists, or any other communication channel.

**"Submitted"** means any form of electronic, verbal, or written communication sent to the Maintainer, including but not limited to communication on electronic mailing lists, source code control systems, and issue tracking systems.

---

## 2. Grant of Copyright License

Subject to the terms and conditions of this Agreement, You hereby grant to the Maintainer and to recipients of software distributed by the Maintainer a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to:

- Reproduce, prepare derivative works of, publicly display, publicly perform, sublicense, and distribute Your Contributions and such derivative works
- Relicense the Contribution under any license, including proprietary licenses

---

## 3. Grant of Patent License

Subject to the terms and conditions of this Agreement, You hereby grant to the Maintainer and to recipients of software distributed by the Maintainer a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work, where such license applies only to those patent claims licensable by You that are necessarily infringed by Your Contribution(s) alone or by combination of Your Contribution(s) with the Work to which such Contribution(s) was submitted.

---

## 4. Representations

You represent that:

### 4.1 Original Work
You are legally entitled to grant the above license. If your employer(s) has rights to intellectual property that you create that includes your Contributions, you represent that:
- You have received permission to make Contributions on behalf of that employer
- Your employer has waived such rights for your Contributions to the Maintainer
- Your employer has executed a separate Corporate CLA with the Maintainer

### 4.2 Third-Party Content
If your Contribution includes or is based on any third-party code, you represent that:
- You have identified all such third-party code in your Contribution
- You have provided complete details of any third-party license or other restriction associated with any part of your Contribution

### 4.3 No Conflicts
Your Contribution does not violate any agreement or obligation you have with any third party.

---

## 5. Support and Warranty Disclaimer

You are not expected to provide support for Your Contributions, except to the extent You desire to provide support. You may provide support for free, for a fee, or not at all.

**UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING, YOU PROVIDE YOUR CONTRIBUTIONS ON AN "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING, WITHOUT LIMITATION, ANY WARRANTIES OR CONDITIONS OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.**

---

## 6. Notification of Changes

You agree to notify the Maintainer of any facts or circumstances of which you become aware that would make these representations inaccurate in any respect.

---

## 7. Moral Rights

To the fullest extent permitted under applicable law, You hereby waive, and agree not to assert, all of Your "moral rights" in or relating to Your Contributions for the benefit of the Maintainer, its assigns, and their respective direct and indirect sublicensees.

---

## 8. Governing Law

This Agreement shall be governed by and construed in accordance with the laws of the jurisdiction in which the Maintainer resides, without regard to its conflict of laws provisions.

---

## 9. Entire Agreement

This Agreement constitutes the entire agreement between the parties with respect to the subject matter hereof and supersedes all prior and contemporaneous agreements and understandings, whether written or oral, relating to such subject matter.

---

## How to Sign This CLA

By submitting a pull request or other Contribution to this Project, you signify your acceptance of this Agreement.

For significant contributions, you may be asked to explicitly confirm your acceptance by:

1. Adding your name to the [CONTRIBUTORS.md](CONTRIBUTORS.md) file (if it exists)
2. Commenting "I have read the CLA and I accept its terms" on your pull request
3. Signing via a CLA bot (if implemented)

---

## Contact

If you have questions about this CLA, please open an issue in the repository or contact the Maintainer directly.

**Maintainer:** Jwadow
**GitHub:** [@jwadow](https://github.com/jwadow)
**Project:** [Kiro Gateway](https://github.com/jwadow/kiro-gateway)

---

*This CLA is based on the Apache Individual Contributor License Agreement and has been modified for this project.*
