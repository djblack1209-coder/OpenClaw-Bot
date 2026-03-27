"""
ClawBot Internal API Schemas
搬运自 freqtrade/rpc/api_server/api_schemas.py 模式
所有请求/响应模型集中定义，供各 router 引用
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
from src.utils import now_et


# ============================================================
# System
# ============================================================

class Ping(BaseModel):
    status: str = "pong"
    version: str = "5.0"


class BotStatus(BaseModel):
    bot_id: str
    username: str
    model: str
    alive: bool
    api_type: str
    message_count: int = 0
    error_count: int = 0
    uptime_seconds: float = 0.0


class SystemStatus(BaseModel):
    uptime_seconds: float
    bots: list[BotStatus]
    ibkr_connected: bool
    ibkr_account: str = ""
    pool_active_sources: int
    pool_total_sources: int
    pool_routing_strategy: str = "balanced"
    total_api_calls: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    memory_entries: int = 0


# ============================================================
# Trading
# ============================================================

class Position(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    market_value: float = 0.0
    side: str = "long"


class PnLSummary(BaseModel):
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    daily_pnl: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_trades: int = 0
    account_value: float = 0.0
    cash: float = 0.0
    buying_power: float = 0.0


class TradingPositions(BaseModel):
    connected: bool
    positions: list[Position] = []
    account_summary: dict = {}


class TradeSignal(BaseModel):
    symbol: str
    signal: str  # BUY/SELL/HOLD
    score: float
    confidence: float = 0.0
    strategy_name: str = ""
    reason: str = ""
    timestamp: str = ""


class TeamVoteResult(BaseModel):
    symbol: str
    consensus_signal: str
    consensus_score: float
    votes: list[dict] = []
    passed: bool = False
    veto_triggered: bool = False
    timestamp: str = ""


class TradingSystemStatus(BaseModel):
    auto_mode: bool = False
    running: bool = False
    scan_interval: int = 30
    risk_manager_active: bool = False
    position_monitor_active: bool = False
    last_scan_time: str = ""
    pending_orders: int = 0
    protections: dict = {}


# ============================================================
# Social
# ============================================================

class SocialPlatformStatus(BaseModel):
    platform: str  # "x" or "xhs"
    connected: bool = False
    last_post_time: str = ""
    posts_today: int = 0
    total_posts: int = 0


class SocialStatus(BaseModel):
    autopilot_running: bool = False
    platforms: list[SocialPlatformStatus] = []
    next_scheduled_action: str = ""
    next_scheduled_time: str = ""
    content_queue_size: int = 0


class ContentDraft(BaseModel):
    id: str = ""
    platform: str = ""
    content: str = ""
    status: str = "draft"  # draft/scheduled/published/failed
    created_at: str = ""
    scheduled_at: str = ""


class SocialAnalytics(BaseModel):
    period: str = "7d"
    total_posts: int = 0
    total_impressions: int = 0
    total_engagements: int = 0
    avg_engagement_rate: float = 0.0
    top_posts: list[dict] = []
    by_platform: dict = {}


# ============================================================
# Memory
# ============================================================

class MemoryEntry(BaseModel):
    key: str
    value: str
    category: str = ""
    importance: float = 1.0
    access_count: int = 0
    similarity: float = 0.0
    match_type: str = ""
    source_bot: str = ""
    created_at: str = ""
    updated_at: str = ""


class MemorySearchResult(BaseModel):
    query: str
    mode: str = "hybrid"
    results: list[MemoryEntry] = []
    total_count: int = 0


class MemoryStats(BaseModel):
    total_entries: int = 0
    by_category: dict = {}
    total_relations: int = 0
    avg_importance: float = 0.0
    engine: str = "sqlite"


# ============================================================
# API Pool
# ============================================================

class PoolStats(BaseModel):
    total_sources: int = 0
    active_sources: int = 0
    routing_strategy: str = "balanced"
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    by_provider: dict = {}


# ============================================================
# Events (WebSocket)
# ============================================================

class WSMessageType(str, Enum):
    STATUS = "status"
    TRADE_SIGNAL = "trade_signal"
    TRADE_EXECUTED = "trade_executed"
    RISK_ALERT = "risk_alert"
    BOT_ERROR = "bot_error"
    SOCIAL_PUBLISHED = "social_published"
    AUTOPILOT_EVENT = "autopilot_event"
    MEMORY_UPDATED = "memory_updated"
    EVOLUTION_PROPOSAL = "evolution_proposal"
    SYNERGY_ACTION = "synergy_action"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Any = None
    timestamp: str = Field(default_factory=lambda: now_et().isoformat())


# ============================================================
# Requests
# ============================================================

class TeamVoteRequest(BaseModel):
    symbol: str
    period: str = "3mo"


class SocialPublishRequest(BaseModel):
    platform: str  # "x", "xhs", "both"
    content: str
    schedule_at: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str
    limit: int = 10
    mode: str = "hybrid"  # keyword/semantic/hybrid
    category: Optional[str] = None


class StatusMsg(BaseModel):
    status: str
    msg: str = ""


# ============================================================
# Shopping (比价)
# ============================================================

class PriceResultSchema(BaseModel):
    title: str
    price: float
    platform: str
    url: str
    shop: str = ""
    historical_low: float = 0.0
    is_deal: bool = False
    source: str = ""


class ComparisonReportSchema(BaseModel):
    success: bool = True
    query: str
    results: list[dict] = []
    best_deal: Optional[dict] = None
    ai_summary: str = ""
    platforms: list[str] = []
    count: int = 0
