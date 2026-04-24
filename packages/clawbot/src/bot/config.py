"""
纯配置层 — 环境变量 + API Key 管理

从 globals.py 提取，打破 globals ↔ history_store/context_manager/shared_memory 循环依赖。
本模块 **不导入任何 src.* 模块**，只依赖标准库和 dotenv。

HI-359: 2026-03-29
"""
import logging
import os
import threading
from pathlib import Path

# ---- dotenv 加载 (.env 文件) ----
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

logger = logging.getLogger(__name__)

if load_dotenv:
    _config_env_path = Path(__file__).resolve().parents[2] / "config" / ".env"
    if _config_env_path.exists():
        load_dotenv(_config_env_path)


# ============ 工具函数 ============

def parse_ids(s):
    """把逗号分隔的数字字符串解析为 int 集合"""
    if not s:
        return set()
    return {int(x.strip()) for x in s.split(',') if x.strip().isdigit()}


# ============ 环境变量 / API 配置 ============

# 管理员用户 ID — 唯一事实源
ALLOWED_USER_IDS = parse_ids(os.getenv('ALLOWED_USER_IDS', ''))

# 硅基流动 API Keys
SILICONFLOW_KEYS = [k.strip() for k in os.getenv('SILICONFLOW_KEYS', '').split(',') if k.strip()]
SILICONFLOW_BASE = os.getenv('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1')
SILICONFLOW_PAID_KEYS = [k.strip() for k in os.getenv('SILICONFLOW_PAID_KEYS', '').split(',') if k.strip()]

# 数据目录 (所有持久化文件的根目录)
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))

# Claude / G4F / Kiro 配置
CLAUDE_KEY = os.getenv('CLAUDE_API_KEY', '')
CLAUDE_BASE = os.getenv('CLAUDE_BASE_URL', 'https://api.anthropic.com/v1')
G4F_BASE = os.getenv('G4F_BASE_URL', 'http://127.0.0.1:18891/v1')
G4F_KEY = os.getenv('G4F_API_KEY', 'dummy')
KIRO_BASE = os.getenv('KIRO_BASE_URL', 'http://127.0.0.1:18793/v1')
KIRO_KEY = os.getenv('KIRO_API_KEY', '')

# 搜索/工具 API
SERPAPI_KEY = os.getenv('SERPAPI_KEY', '')
BRAVE_SEARCH_API_KEY = os.getenv('BRAVE_SEARCH_API_KEY', '')

# Composio 外部服务集成 (250+ 应用: Gmail/Calendar/Slack/GitHub 等)
COMPOSIO_API_KEY = os.getenv('COMPOSIO_API_KEY', '')

# Skyvern 视觉 RPA (11k⭐, 截图 + LLM 理解页面)
SKYVERN_API_KEY = os.getenv('SKYVERN_API_KEY', '')


# ============ 硅基流动 Key 轮转管理 ============

current_sf_key_idx = 0
_sf_init_balance = float(os.getenv("SF_INITIAL_BALANCE", "13.0"))
sf_key_balances = {k: _sf_init_balance for k in SILICONFLOW_KEYS}
LOW_BALANCE_THRESHOLD = float(os.getenv('SF_LOW_BALANCE', '1.0'))

# 保护 Key 轮转的线程锁（asyncio 事件循环 + BackgroundScheduler 线程共用）
_sf_lock = threading.Lock()


def get_siliconflow_key():
    """获取可用的硅基流动 Key，自动跳过低余额的（线程安全）"""
    global current_sf_key_idx
    if not SILICONFLOW_KEYS:
        return None
    with _sf_lock:
        for _ in range(len(SILICONFLOW_KEYS)):
            key = SILICONFLOW_KEYS[current_sf_key_idx % len(SILICONFLOW_KEYS)]
            current_sf_key_idx += 1
            balance = sf_key_balances.get(key, 0)
            if balance > LOW_BALANCE_THRESHOLD:
                return key
    logger.warning("所有 API Key 余额不足！")
    return SILICONFLOW_KEYS[0] if SILICONFLOW_KEYS else None


def update_key_balance(key: str, cost: float):
    """扣减指定 Key 的余额，低于阈值时发出警告（线程安全）"""
    with _sf_lock:
        if key in sf_key_balances:
            sf_key_balances[key] = max(0, sf_key_balances[key] - cost)
            if sf_key_balances[key] < LOW_BALANCE_THRESHOLD:
                logger.warning(f"API Key {key[:4]}... 余额不足: {sf_key_balances[key]:.2f}元")


def get_total_balance() -> float:
    """返回所有硅基流动 Key 的余额总和"""
    with _sf_lock:
        return sum(sf_key_balances.values())


def mark_key_exhausted(key: str):
    """API 返回余额不足错误时，标记该 Key 为耗尽（线程安全）"""
    with _sf_lock:
        if key in sf_key_balances:
            sf_key_balances[key] = 0
            logger.warning(f"API Key {key[:4]}... 已标记为耗尽（API返回余额不足）")
