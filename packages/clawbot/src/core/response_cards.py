"""
OpenClaw OMEGA — 统一响应卡片系统 (ResponseCard)
借鉴 Agno (38.8k⭐) 的 Pydantic 结构化输出 + LobeHub (74k⭐) 的 Block 渲染模式。

核心理念:
  每个模块的输出都是一个 ResponseCard → 自带 to_telegram() + action_buttons()
  Gateway 层只需: card.to_telegram() + card.action_buttons()

与现有系统的关系:
  - 泛化 telegram_ux.py 中已有的 format_trade_card/format_portfolio_card/format_quote_card
  - 被 brain.py 的所有 _exec_* 函数返回
  - 被 gateway/telegram_gateway.py 的 _format_result() 消费
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


# ── 基础卡片 ──────────────────────────────────────────

@dataclass
class ResponseCard:
    """所有响应卡片的基类"""
    card_type: str = "generic"
    title: str = ""
    body: str = ""
    footer: str = ""
    task_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))

    def to_telegram(self) -> str:
        """渲染为 Telegram HTML 格式消息"""
        parts = []
        if self.title:
            parts.append(f"<b>{self.title}</b>")
            parts.append("━━━━━━━━━━━━━━━")
        if self.body:
            parts.append(self.body)
        if self.footer:
            parts.append(f"\n<i>{self.footer}</i>")
        return "\n".join(parts) or "（无内容）"

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        """生成 Inline Keyboard，子类覆写"""
        return None

    def to_dict(self) -> Dict:
        return {
            "card_type": self.card_type,
            "title": self.title,
            "body": self.body,
            "footer": self.footer,
        }


# ── 投资分析卡片 ──────────────────────────────────────

@dataclass
class InvestmentAnalysisCard(ResponseCard):
    """投资团队分析结果卡片"""
    card_type: str = "investment_analysis"
    symbol: str = ""
    recommendation: str = "hold"  # buy / sell / hold
    confidence: float = 0.0
    target_price: float = 0.0
    stop_loss: float = 0.0
    current_price: float = 0.0
    position_size_pct: float = 0.0
    veto: bool = False
    veto_reason: str = ""
    research_score: float = 0.0
    ta_score: float = 0.0
    quant_score: float = 0.0
    research_summary: str = ""
    ta_summary: str = ""
    quant_summary: str = ""
    risk_assessment: str = ""

    def to_telegram(self) -> str:
        rec_emoji = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "⚪ 观望"}
        rec_text = rec_emoji.get(self.recommendation, f"⚪ {self.recommendation.upper()}")

        # 星级评分
        def stars(score): return "⭐" * max(1, int(score / 2)) + f" {score:.1f}"

        lines = [
            f"📊 <b>投资分析: {self.symbol}</b>",
            "━━━━━━━━━━━━━━━",
            "",
            f"📈 研究员: {stars(self.research_score)}",
            f"   {self.research_summary[:60]}" if self.research_summary else "",
            "",
            f"📉 技术面: {stars(self.ta_score)}",
            f"   {self.ta_summary[:60]}" if self.ta_summary else "",
            "",
            f"🔢 量化: {stars(self.quant_score)}",
            f"   {self.quant_summary[:60]}" if self.quant_summary else "",
            "",
        ]

        # 风控
        if self.veto:
            lines.append(f"🛡 风控: ❌ <b>否决</b> — {self.veto_reason}")
        else:
            lines.append(f"🛡 风控: ✅ 通过 {self.risk_assessment[:40]}")

        lines.extend([
            "",
            "━━━━━━━━━━━━━━━",
            f"💡 <b>建议: {rec_text}</b>",
            f"🎯 置信度: {self.confidence:.0%}",
        ])

        if self.target_price > 0:
            gain = (self.target_price / self.current_price - 1) * 100 if self.current_price > 0 else 0
            lines.append(f"📈 目标: ${self.target_price:.2f} ({gain:+.1f}%)")
        if self.stop_loss > 0:
            loss = (self.stop_loss / self.current_price - 1) * 100 if self.current_price > 0 else 0
            lines.append(f"🛑 止损: ${self.stop_loss:.2f} ({loss:+.1f}%)")
        if self.position_size_pct > 0:
            lines.append(f"📊 建议仓位: {self.position_size_pct:.1%}")

        return "\n".join(l for l in lines if l is not None)

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        tid = self.task_id or "0"
        buttons = []

        if self.recommendation == "buy" and not self.veto:
            buttons.append([
                InlineKeyboardButton("✅ 确认买入", callback_data=f"trade:buy:{self.symbol}"),
                InlineKeyboardButton("✏️ 调仓位", callback_data=f"trade:size:{self.symbol}"),
            ])

        buttons.append([
            InlineKeyboardButton("📊 回测验证", callback_data=f"bt:ma:{self.symbol}"),
            InlineKeyboardButton("📈 详细TA", callback_data=f"ta:detail:{self.symbol}"),
        ])
        buttons.append([
            InlineKeyboardButton("🔄 重新分析", callback_data=f"analyze:{self.symbol}"),
            InlineKeyboardButton("📰 相关新闻", callback_data=f"news:{self.symbol}"),
        ])

        return InlineKeyboardMarkup(buttons)


# ── 回测结果卡片 ──────────────────────────────────────

@dataclass
class BacktestCard(ResponseCard):
    """回测结果卡片"""
    card_type: str = "backtest"
    symbol: str = ""
    strategy: str = ""
    period: str = ""
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    annual_return: float = 0.0

    def to_telegram(self) -> str:
        ret_emoji = "🟢" if self.total_return >= 0 else "🔴"
        sharpe_emoji = "✅" if self.sharpe_ratio > 1.5 else "⚠️" if self.sharpe_ratio > 1.0 else "❌"

        return (
            f"📈 <b>回测: {self.symbol} ({self.strategy})</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 区间: {self.period}\n"
            f"\n"
            f"{ret_emoji} 总收益: <b>{self.total_return:.2%}</b>\n"
            f"📊 年化: {self.annual_return:.2%}\n"
            f"{sharpe_emoji} 夏普: {self.sharpe_ratio:.2f}\n"
            f"📉 最大回撤: {self.max_drawdown:.2%}\n"
            f"🎯 胜率: {self.win_rate:.2%} ({self.num_trades}笔)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{'✅ 策略可用' if self.sharpe_ratio > 1.0 and self.max_drawdown > -0.20 else '⚠️ 需谨慎'}"
        )

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 换RSI策略", callback_data=f"bt:rsi:{self.symbol}"),
                InlineKeyboardButton("📊 多策略对比", callback_data=f"bt:compare:{self.symbol}"),
            ],
            [
                InlineKeyboardButton("📈 实盘分析", callback_data=f"analyze:{self.symbol}"),
            ],
        ])


# ── 热点/社媒卡片 ──────────────────────────────────────

@dataclass
class TrendingCard(ResponseCard):
    """热点趋势卡片"""
    card_type: str = "trending"
    platform: str = ""
    topics: List[Dict] = field(default_factory=list)

    def to_telegram(self) -> str:
        platform_emoji = {"weibo": "🔥", "baidu": "🔍", "zhihu": "💬", "x": "𝕏"}.get(
            self.platform, "📰"
        )
        lines = [f"{platform_emoji} <b>热点趋势</b>", ""]

        for i, topic in enumerate(self.topics[:10], 1):
            title = topic.get("title", topic.get("name", ""))
            hot = topic.get("hot", topic.get("score", ""))
            hot_str = f" ({hot})" if hot else ""
            lines.append(f"  {i}. {title}{hot_str}")

        return "\n".join(lines)

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        if not self.topics:
            return None
        buttons = []
        for topic in self.topics[:3]:
            title = topic.get("title", topic.get("name", ""))[:15]
            buttons.append(
                InlineKeyboardButton(f"📝 写{title}", callback_data=f"post:{title[:20]}")
            )
        return InlineKeyboardMarkup([buttons])


# ── 系统状态卡片 ──────────────────────────────────────

@dataclass
class SystemStatusCard(ResponseCard):
    """系统状态卡片"""
    card_type: str = "system_status"
    bots_alive: int = 0
    bots_total: int = 0
    api_pool_size: int = 0
    memory_entries: int = 0
    broker_connected: bool = False
    brain_active_tasks: int = 0
    daily_cost: float = 0.0
    daily_budget: float = 50.0
    uptime_hours: float = 0.0

    def to_telegram(self) -> str:
        cost_pct = self.daily_cost / self.daily_budget * 100 if self.daily_budget > 0 else 0
        cost_bar = "█" * max(1, int(cost_pct / 10)) + "░" * (10 - max(1, int(cost_pct / 10)))

        return (
            f"🦞 <b>OpenClaw OMEGA 状态</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"\n"
            f"🤖 Bot: {self.bots_alive}/{self.bots_total} 在线\n"
            f"🧠 Brain: {self.brain_active_tasks} 个活跃任务\n"
            f"🔌 API池: {self.api_pool_size} 个模型\n"
            f"📝 记忆: {self.memory_entries} 条\n"
            f"📈 券商: {'🟢 已连接' if self.broker_connected else '⚪ 未连接'}\n"
            f"\n"
            f"💰 今日费用: ${self.daily_cost:.4f} / ${self.daily_budget:.2f}\n"
            f"   {cost_bar} {cost_pct:.1f}%"
        )

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 持仓", callback_data="cmd:portfolio"),
                InlineKeyboardButton("💰 费用详情", callback_data="cmd:cost"),
            ],
            [
                InlineKeyboardButton("🔄 进化扫描", callback_data="cmd:evolve"),
                InlineKeyboardButton("📋 任务列表", callback_data="cmd:tasks"),
            ],
        ])


# ── 进化提案卡片 ──────────────────────────────────────

@dataclass
class EvolutionCard(ResponseCard):
    """进化提案卡片"""
    card_type: str = "evolution"
    proposals_count: int = 0
    proposals: List[Dict] = field(default_factory=list)

    def to_telegram(self) -> str:
        lines = [
            f"🧬 <b>进化扫描完成</b>",
            f"发现 {self.proposals_count} 个候选项目",
            "",
        ]
        for p in self.proposals[:5]:
            name = p.get("repo_name", "?")
            stars = p.get("stars", 0)
            score = p.get("value_score", 0)
            module = p.get("target_module", "?")
            status = p.get("status", "proposed")
            icon = {"proposed": "🆕", "approved": "✅", "rejected": "❌"}.get(status, "⬜")
            lines.append(f"  {icon} <b>{name}</b> ⭐{stars}")
            lines.append(f"     价值:{score:.1f} | 模块:{module}")

        return "\n".join(lines)

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        if not self.proposals:
            return None
        buttons = []
        for p in self.proposals[:3]:
            pid = p.get("id", "")[:8]
            name = p.get("repo_name", "?")[:12]
            buttons.append([
                InlineKeyboardButton(f"✅ 批准 {name}", callback_data=f"evo:approve:{pid}"),
                InlineKeyboardButton(f"❌ 拒绝", callback_data=f"evo:reject:{pid}"),
            ])
        return InlineKeyboardMarkup(buttons)


# ── 通用信息卡片 ──────────────────────────────────────

@dataclass
class InfoCard(ResponseCard):
    """通用信息回答卡片"""
    card_type: str = "info"
    answer: str = ""
    sources: List[str] = field(default_factory=list)

    def to_telegram(self) -> str:
        lines = [self.answer or self.body]
        if self.sources:
            lines.append("")
            lines.append("<i>来源:</i>")
            for s in self.sources[:3]:
                lines.append(f"  • {s[:60]}")
        return "\n".join(lines)


# ── 错误/追问卡片 ──────────────────────────────────────

@dataclass
class ClarificationCard(ResponseCard):
    """追问卡片 — 需要用户补充信息"""
    card_type: str = "clarification"
    goal: str = ""
    missing_params: List[str] = field(default_factory=list)
    partial_results: str = ""  # 已完成的部分

    def to_telegram(self) -> str:
        lines = [f"💬 了解，你需要: <b>{self.goal}</b>"]
        if self.partial_results:
            lines.extend(["", self.partial_results])
        if self.missing_params:
            lines.extend(["", "请补充以下信息:"])
            for p in self.missing_params:
                lines.append(f"  • {p}")
        return "\n".join(lines)

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        """根据参数类型生成快捷按钮"""
        if not self.missing_params:
            return None

        buttons = []
        tid = self.task_id or "0"

        for param in self.missing_params[:3]:
            param_lower = param.lower()
            if any(k in param_lower for k in ("time", "date", "日期", "时间")):
                buttons.append([
                    InlineKeyboardButton("今天", callback_data=f"{tid}:{param}:today"),
                    InlineKeyboardButton("明天", callback_data=f"{tid}:{param}:tomorrow"),
                    InlineKeyboardButton("周末", callback_data=f"{tid}:{param}:weekend"),
                ])
            elif any(k in param_lower for k in ("count", "人", "位")):
                buttons.append([
                    InlineKeyboardButton("1人", callback_data=f"{tid}:{param}:1"),
                    InlineKeyboardButton("2人", callback_data=f"{tid}:{param}:2"),
                    InlineKeyboardButton("3-4人", callback_data=f"{tid}:{param}:4"),
                    InlineKeyboardButton("5+", callback_data=f"{tid}:{param}:5"),
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(f"补充 {param}", callback_data=f"{tid}:{param}:ask"),
                ])

        buttons.append([
            InlineKeyboardButton("❌ 取消", callback_data=f"{tid}:cancel:0"),
        ])
        return InlineKeyboardMarkup(buttons)


@dataclass
class ErrorCard(ResponseCard):
    """错误卡片"""
    card_type: str = "error"
    error_message: str = ""
    recoverable: bool = True

    def to_telegram(self) -> str:
        icon = "⚠️" if self.recoverable else "❌"
        lines = [f"{icon} <b>执行出错</b>", "", self.error_message[:300]]
        if self.recoverable:
            lines.append("\n<i>可以重试或换个方式表达</i>")
        return "\n".join(lines)

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        if not self.recoverable:
            return None
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 重试", callback_data=f"retry:{self.task_id}"),
                InlineKeyboardButton("💬 人工帮助", callback_data="cmd:help"),
            ],
        ])


# ── 购物比价卡片 ──────────────────────────────────────

@dataclass
class ShoppingCard(ResponseCard):
    """购物比价结果卡片"""
    card_type: str = "shopping"
    product: str = ""
    products: List[Dict] = field(default_factory=list)
    recommendation: str = ""
    best_deal: str = ""
    tips: str = ""

    def to_telegram(self) -> str:
        lines = [f"🛒 <b>比价: {self.product}</b>", "━━━━━━━━━━━━━━━"]

        for i, p in enumerate(self.products[:8], 1):
            name = p.get("name", "")[:40]
            price = p.get("price", "未知")
            platform = p.get("platform", "")
            note = p.get("note", "")
            lines.append(f"\n{i}. <b>{name}</b>")
            lines.append(f"   💰 {price} | 📍 {platform}")
            if note:
                lines.append(f"   📝 {note[:40]}")

        if self.best_deal:
            lines.extend(["", f"🏆 <b>最佳: {self.best_deal}</b>"])
        if self.recommendation:
            lines.extend(["", f"💡 {self.recommendation[:100]}"])
        if self.tips:
            lines.extend(["", f"🔑 {self.tips[:80]}"])

        return "\n".join(lines)

    def action_buttons(self) -> Optional[InlineKeyboardMarkup]:
        buttons = []
        if self.products:
            first_name = self.products[0].get("name", "商品")[:10]
            buttons.append([
                InlineKeyboardButton(f"🔄 重新比价", callback_data=f"shop:refresh:{self.product[:20]}"),
            ])
        return InlineKeyboardMarkup(buttons) if buttons else None


# ── 工厂函数 — 从 Brain 结果自动创建对应卡片 ──────────

def card_from_brain_result(result) -> ResponseCard:
    """
    从 Brain 的 TaskResult 自动创建对应类型的 ResponseCard。

    这是 Gateway 层唯一需要调用的函数:
        card = card_from_brain_result(result)
        await msg.reply_html(card.to_telegram(), reply_markup=card.action_buttons())
    """
    if result.error:
        return ErrorCard(
            error_message=result.error,
            task_id=result.task_id,
            recoverable=True,
        )

    if result.needs_clarification:
        return ClarificationCard(
            goal=result.intent.goal if result.intent else "",
            missing_params=result.clarification_params,
            task_id=result.task_id,
        )

    intent = result.intent
    if intent is None:
        return InfoCard(answer=str(result.final_result)[:500])

    task_type = intent.task_type.value if intent else "unknown"
    data = result.final_result or {}

    # 投资分析
    if task_type == "investment":
        return _build_investment_card(data, result.task_id, intent)

    # 系统状态
    if task_type == "system":
        return _build_system_card(data)

    # 进化
    if task_type == "evolution":
        return _build_evolution_card(data)

    # 购物比价
    if task_type == "shopping":
        return _build_shopping_card(data, intent)

    # 生活服务（天气等）
    if task_type == "life":
        return _build_life_card(data, intent)

    # 社媒
    if task_type == "social":
        return _build_social_card(data, intent)

    # 通用信息
    if task_type == "info":
        answer = ""
        for v in data.values():
            if isinstance(v, dict) and "answer" in v:
                answer = v["answer"]
                break
        return InfoCard(answer=answer or str(data)[:500])

    # 默认
    return InfoCard(
        title=intent.goal if intent else "结果",
        answer=_format_dict_readable(data),
    )


def _build_investment_card(data: Dict, task_id: str, intent) -> ResponseCard:
    """从投资分析结果构建卡片 — 处理多种数据格式"""
    symbol = intent.known_params.get("symbol_hint", intent.known_params.get("symbol_raw", "?"))

    # 如果是从 TeamAnalysis.to_dict() 来的
    if "final_recommendation" in data:
        return InvestmentAnalysisCard(
            symbol=data.get("symbol", symbol),
            recommendation=data.get("final_recommendation", "hold"),
            confidence=data.get("confidence", 0),
            target_price=data.get("target_price", 0),
            stop_loss=data.get("stop_loss", 0),
            position_size_pct=data.get("position_size_pct", 0),
            veto=data.get("veto", False),
            veto_reason=data.get("veto_reason", ""),
            research_score=_safe_score(data, "research"),
            ta_score=_safe_score(data, "ta"),
            quant_score=_safe_score(data, "quant"),
            research_summary=_safe_summary(data, "research"),
            ta_summary=_safe_summary(data, "ta"),
            quant_summary=_safe_summary(data, "quant"),
            task_id=task_id,
        )

    # 从 brain 的分步结果构建（每个 key 是一个节点 id）
    research_data = data.get("research", {})
    ta_data = data.get("ta", {})
    quant_data = data.get("quant", {})
    risk_data = data.get("risk", {})
    decision_data = data.get("decision", {})

    # 提取各角色的摘要
    r_summary = _extract_node_summary(research_data)
    t_summary = _extract_node_summary(ta_data)
    q_summary = _extract_node_summary(quant_data)

    # 提取评分
    r_score = _extract_node_score(research_data)
    t_score = _extract_node_score(ta_data)
    q_score = _extract_node_score(quant_data)

    # 风控
    veto = False
    veto_reason = ""
    if isinstance(risk_data, dict):
        veto = not risk_data.get("approved", True)
        veto_reason = risk_data.get("note", risk_data.get("veto_reason", ""))

    # 最终决策
    recommendation = "hold"
    confidence = 0.0
    if isinstance(decision_data, dict):
        recommendation = decision_data.get("decision", decision_data.get("recommendation", "hold"))
        confidence = decision_data.get("confidence", 0)

    return InvestmentAnalysisCard(
        symbol=symbol,
        recommendation=recommendation,
        confidence=confidence,
        veto=veto,
        veto_reason=veto_reason,
        research_score=r_score,
        ta_score=t_score,
        quant_score=q_score,
        research_summary=r_summary,
        ta_summary=t_summary,
        quant_summary=q_summary,
        risk_assessment=str(risk_data.get("note", ""))[:40] if isinstance(risk_data, dict) else "",
        task_id=task_id,
    )


def _safe_score(data: Dict, key: str) -> float:
    """安全提取评分"""
    v = data.get(key)
    if isinstance(v, dict):
        return float(v.get("score", 0))
    return 0.0


def _safe_summary(data: Dict, key: str) -> str:
    """安全提取摘要"""
    v = data.get(key)
    if isinstance(v, dict):
        return v.get("reasoning", v.get("recommendation", ""))[:60]
    return ""


def _extract_node_summary(node_data) -> str:
    """从一个节点结果提取人类可读摘要"""
    if not isinstance(node_data, dict):
        return str(node_data)[:60] if node_data else ""

    # 优先用 reasoning > note > recommendation > 第一个有意义的值
    for key in ("reasoning", "note", "recommendation", "key_signal", "trend"):
        v = node_data.get(key)
        if v and isinstance(v, str) and len(v) > 2:
            return v[:60]

    # data 子字段
    inner = node_data.get("data", {})
    if isinstance(inner, dict):
        for key in ("reasoning", "note", "recommendation", "key_signal"):
            v = inner.get(key)
            if v and isinstance(v, str) and len(v) > 2:
                return v[:60]

    # 最后降级: source
    src = node_data.get("source", "")
    if src:
        return f"来源: {src}"
    return ""


def _extract_node_score(node_data) -> float:
    """从一个节点结果提取评分"""
    if not isinstance(node_data, dict):
        return 0.0

    for key in ("score", "value_score", "technical_score"):
        v = node_data.get(key)
        if isinstance(v, (int, float)):
            return float(v)

    inner = node_data.get("data", {})
    if isinstance(inner, dict):
        for key in ("score", "value_score"):
            v = inner.get(key)
            if isinstance(v, (int, float)):
                return float(v)

    return 0.0


def _build_shopping_card(data: Dict, intent) -> ShoppingCard:
    """从购物比价结果构建卡片"""
    product = intent.known_params.get("product_hint", intent.goal)

    # 从 Brain 的分步结果中提取
    compare_data = data.get("compare", data)
    if isinstance(compare_data, dict):
        products = compare_data.get("products", [])
        recommendation = compare_data.get("recommendation", "")
        best_deal = compare_data.get("best_deal", "")
        tips = compare_data.get("tips", "")

        # 如果是原始LLM文本
        if not products and "raw" in compare_data:
            return ShoppingCard(
                product=product,
                recommendation=compare_data.get("raw", "")[:200],
            )

        return ShoppingCard(
            product=product,
            products=products if isinstance(products, list) else [],
            recommendation=str(recommendation)[:100],
            best_deal=str(best_deal)[:60],
            tips=str(tips)[:80],
        )

    return ShoppingCard(product=product, recommendation=str(data)[:200])


def _build_life_card(data: Dict, intent) -> ResponseCard:
    """从生活服务结果构建卡片（天气等）"""
    # 检查天气数据
    for v in data.values():
        if isinstance(v, dict) and v.get("source") == "weather":
            city = v.get("city", "")
            cur = v.get("current", {})
            forecasts = v.get("forecasts", [])
            text = v.get("text", "")
            if text:
                return InfoCard(answer=text)
            # 从结构化数据构建
            lines = [f"🌤 <b>{city} 天气</b>"]
            if cur:
                lines.append(f"当前: {cur.get('temp','')}°C {cur.get('weather','')} 湿度{cur.get('humidity','')}%")
            for f in forecasts[:3]:
                lines.append(f"  {f.get('date','')} {f.get('dayweather','')} {f.get('nighttemp','')}-{f.get('daytemp','')}°C")
            return InfoCard(answer="\n".join(lines))

    return InfoCard(title=intent.goal, answer=_format_dict_readable(data))


def _build_system_card(data: Dict) -> SystemStatusCard:
    """从系统状态数据构建卡片"""
    status_data = data.get("status", data)
    if isinstance(status_data, dict) and "status" in status_data:
        status_data = status_data.get("status", status_data)

    bots = status_data.get("bots", []) if isinstance(status_data, dict) else []
    pool = status_data.get("api_pool", {}) if isinstance(status_data, dict) else {}
    memory = status_data.get("memory", {}) if isinstance(status_data, dict) else {}
    broker = status_data.get("broker", {}) if isinstance(status_data, dict) else {}

    return SystemStatusCard(
        bots_alive=sum(1 for b in bots if isinstance(b, dict) and b.get("alive")) if isinstance(bots, list) else 0,
        bots_total=len(bots) if isinstance(bots, list) else 0,
        api_pool_size=pool.get("total_sources", 0) if isinstance(pool, dict) else 0,
        memory_entries=memory.get("total_entries", 0) if isinstance(memory, dict) else 0,
        broker_connected=broker.get("connected", False) if isinstance(broker, dict) else False,
    )


def _build_evolution_card(data: Dict) -> EvolutionCard:
    """从进化扫描结果构建卡片"""
    scan = data.get("scan", data)
    if isinstance(scan, dict):
        return EvolutionCard(
            proposals_count=scan.get("proposals_count", 0),
            proposals=scan.get("proposals", []),
        )
    return EvolutionCard()


def _build_social_card(data: Dict, intent) -> ResponseCard:
    """从社媒结果构建卡片"""
    # 热点趋势
    if "topics" in data or any("topics" in str(v) for v in data.values()):
        topics = []
        for v in data.values():
            if isinstance(v, dict) and "topics" in v:
                topics = v["topics"]
                break
        return TrendingCard(topics=topics)

    return InfoCard(title=intent.goal, answer=_format_dict_readable(data))


def _format_dict_readable(data: Dict, max_depth: int = 2) -> str:
    """将嵌套 dict 格式化为人类可读文本"""
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            if "note" in value:
                lines.append(f"• {key}: {value['note']}")
            elif "answer" in value:
                lines.append(f"{value['answer']}")
            elif "error" in value:
                lines.append(f"⚠️ {key}: {value['error']}")
            else:
                lines.append(f"• {key}: {str(value)[:100]}")
        elif isinstance(value, list):
            lines.append(f"• {key}: {len(value)} 项")
        else:
            lines.append(f"• {key}: {str(value)[:100]}")
    return "\n".join(lines) if lines else "（无数据）"
