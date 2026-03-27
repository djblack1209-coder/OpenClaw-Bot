"""
启动时配置验证 — 在 Bot 启动前检查所有必要环境变量和文件。

在 multi_main.py 中调用 validate_startup_config()，输出警告并在严重缺失时阻止启动。
"""
import os
from pathlib import Path
from typing import List, Tuple

import logging

logger = logging.getLogger(__name__)

# ── 必须设置的环境变量 ──
REQUIRED_ENV_VARS: List[Tuple[str, str]] = [
    ("ALLOWED_USER_IDS", "管理员 Telegram user ID — 用于权限控制"),
]

# ── 至少需要一个的环境变量组 ──
REQUIRED_ONE_OF: List[Tuple[List[str], str]] = [
    # 至少一个 Bot Token (否则系统无法接收消息)
    (
        [
            "QWEN235B_TOKEN",
            "GPTOSS_TOKEN",
            "CLAUDE_SONNET_TOKEN",
            "CLAUDE_HAIKU_TOKEN",
            "DEEPSEEK_V3_TOKEN",
            "CLAUDE_OPUS_TOKEN",
            "FREE_LLM_TOKEN",
        ],
        "至少一个 Telegram Bot Token — 否则无法接收/发送消息",
    ),
    # 至少一个 LLM 提供商 Key (否则 AI 功能不可用)
    (
        [
            "SILICONFLOW_KEYS",
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "CEREBRAS_API_KEY",
            "MISTRAL_API_KEY",
            "COHERE_API_KEY",
            "GITHUB_MODELS_TOKEN",
            "NVIDIA_NIM_API_KEY",
            "SAMBANOVA_API_KEY",
            "SILICONFLOW_UNLIMITED_KEY",
            "GPT_API_FREE_KEY",
        ],
        "至少一个 LLM 提供商 API Key — 否则 AI 对话功能不可用",
    ),
]

# ── 必须存在的文件 (相对于 packages/clawbot/) ──
REQUIRED_FILES: List[Tuple[str, str]] = [
    ("config/.env", "环境变量配置文件 — 包含所有 API Key 和 Bot Token"),
    ("config/omega.yaml", "OMEGA v2.0 系统配置文件"),
]

# ── 推荐设置的环境变量 (缺失只警告，不阻止启动) ──
RECOMMENDED_ENV_VARS: List[Tuple[str, str]] = [
    ("ADMIN_CHAT_ID", "管理员 chat ID — 缺失则无法接收 Telegram 告警通知"),
    ("LANGFUSE_SECRET_KEY", "Langfuse 追踪 — 缺失则 LLM 调用无法追踪"),
]


def validate_startup_config() -> Tuple[List[str], List[str]]:
    """
    验证启动配置。

    Returns:
        (errors, warnings) — errors 非空则应阻止启动，warnings 仅输出日志。
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. 必须的环境变量
    for var, desc in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            warnings.append(f"环境变量 {var} 未设置 — {desc}")

    # 2. 至少需要一个的组
    for var_group, desc in REQUIRED_ONE_OF:
        if not any(os.getenv(v) for v in var_group):
            errors.append(f"至少需要一个: {', '.join(var_group[:4])}... — {desc}")

    # 3. 必须存在的文件
    base = Path(__file__).resolve().parent.parent.parent  # packages/clawbot/
    for rel_path, desc in REQUIRED_FILES:
        full_path = base / rel_path
        if not full_path.exists():
            if rel_path == "config/omega.yaml":
                # omega.yaml 缺失不阻塞 — brain.py 有内置默认值
                warnings.append(f"文件不存在: {rel_path} — {desc} (将使用默认配置)")
            else:
                errors.append(f"文件不存在: {rel_path} — {desc}")

    # 4. 推荐设置的环境变量
    for var, desc in RECOMMENDED_ENV_VARS:
        if not os.getenv(var):
            warnings.append(f"推荐设置: {var} — {desc}")

    # 5. 特殊检查: Bot Token 必须在 .env 中设置
    if not os.getenv("FREE_LLM_TOKEN"):
        warnings.append(
            "FREE_LLM_TOKEN 未设置 — 请在 .env 中配置 Free LLM Bot 的 Telegram Token"
        )

    return errors, warnings


def log_validation_results(errors: List[str], warnings: List[str]) -> bool:
    """
    输出验证结果到日志。

    Returns:
        True = 可以继续启动, False = 应停止启动。
    """
    if not errors and not warnings:
        logger.info("  配置验证通过 ✓")
        return True

    for w in warnings:
        logger.warning("  [配置] ⚠️ %s", w)

    for e in errors:
        logger.error("  [配置] 🔴 %s", e)

    if errors:
        logger.critical(
            "  [配置] 发现 %d 个严重配置问题 — 系统可能无法正常运行",
            len(errors),
        )
        return False

    return True
