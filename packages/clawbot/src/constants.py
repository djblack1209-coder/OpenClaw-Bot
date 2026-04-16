"""
全局常量 — 各模块共享的 HTTP 请求头、版本号、平台限制、Bot ID、模型族等。

统一管理 User-Agent、Bot ID、Model Family 字符串，
避免散落在各文件中导致拼写不一致或更换模型时需逐文件修改。
更新 Chrome 版本、切换模型只需改此处。
"""

# ── Telegram 消息长度限制 ──────────────────────────────────────
# 真实 API 上限（超过会被 Telegram 服务器拒绝）
TG_MSG_LIMIT = 4096
# 安全发送上限（留 96 字符给 footer / bot 签名 / HTML 标签等）
TG_SAFE_LENGTH = 4000

# 通用 Web 抓取 User-Agent（macOS Chrome）
# 用于 GitHub trending、SMZDM 比价、社交热搜等公开页面抓取
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

# 闲鱼/咸鱼专用 User-Agent（Windows Chrome）
# 闲鱼 Web 端 (goofish.com) 对 UA 有检测，需要模拟 Windows 浏览器
XIANYU_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36"

# ── Bot ID 常量 ─────────────────────────────────────────────────
# 7 个 Bot 的内部标识符，对应 multi_main.py 中注册的 bot_id
# 修改 bot 名称/增删 bot 只需改此处
BOT_QWEN = "qwen235b"  # 通义千问 235B (主力免费模型)
BOT_DEEPSEEK = "deepseek_v3"  # DeepSeek V3 (编程/数学)
BOT_GPTOSS = "gptoss"  # GPT 开源替代 (快速通用)
BOT_CLAUDE_HAIKU = "claude_haiku"  # Claude Haiku (创意/轻量)
BOT_CLAUDE_SONNET = "claude_sonnet"  # Claude Sonnet (复杂推理)
BOT_CLAUDE_OPUS = "claude_opus"  # Claude Opus (终极分析)
BOT_FREE_LLM = "free_llm"  # 免费 LLM 兜底

# ── Model Family 常量 ──────────────────────────────────────────
# model_family 参数值，决定 litellm_router 走哪条降级链
# 修改降级链路由只需改此处映射
FAMILY_QWEN = "qwen"  # 千问系免费链 (SiliconFlow → Groq → ...)
FAMILY_DEEPSEEK = "deepseek"  # DeepSeek 链
FAMILY_CLAUDE = "claude"  # Claude 链 (Anthropic → g4f)
FAMILY_G4F = "g4f"  # 纯免费 g4f 兜底
FAMILY_GEMINI = "gemini"  # Google Gemini 链
FAMILY_GPT_OSS = "gpt-oss"  # GPT 开源替代链
FAMILY_FAST = "fast"  # 快速推理链 (Groq 8b → Cerebras → g4f)

# ── 图片生成模型 Key ────────────────────────────────────────────
# image_tool.py 中使用的模型 key
IMG_MODEL_FLUX = "flux"  # FLUX.1-schnell (默认)
IMG_MODEL_SD3 = "sd3"  # Stable Diffusion 3
IMG_MODEL_SDXL = "sdxl"  # Stable Diffusion XL

# ── 交易相关用户提示消息（消除跨文件重复）──────────────────────
# HI-381: 统一频繁使用的错误/警告消息，避免拼写不一致
ERR_RISK_NOT_INIT = "⚠️ 风控系统未初始化，无法执行交易。"
ERR_QTY_POSITIVE = "⚠️ 数量必须为正数。"
ERR_ORDER_PENDING = "⚠️ 订单已提交但尚未成交，请稍后查看 /portfolio。"
ERR_LIVE_UNAVAILABLE = "⚠️ 实盘暂不可用，已为您在模拟组合中执行"
ERR_LIMIT_PRICE_INVALID = "⚠️ 限价格式无效 '{price}'，将使用市价单"
