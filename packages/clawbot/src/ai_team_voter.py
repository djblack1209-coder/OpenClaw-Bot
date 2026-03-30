"""
ClawBot AI 团队投票决策模块 v1.1

6位AI分析师对候选标的独立分析后投票，多数决定是否交易。
每位分析师有明确角色和评分维度，最终通过加权投票产出决策。

投票规则:
- 6位分析师各自独立给出 BUY / HOLD / SKIP 投票
- BUY 票数 >= 4 (含) 才执行交易（6人制需2/3多数）
- 风控官(DeepSeek) 和 首席策略师(Opus) 拥有一票否决权
- 每位分析师同时给出 1-10 的信心分
- 最终置信度 = 加权平均信心分 / 10
"""
import asyncio
import logging
import os
import re
import statistics
from dataclasses import dataclass, field

from config.prompts import INVEST_VOTE_PROMPTS
from src.execution._utils import safe_float
from src.utils import env_int, env_float
from src.constants import (
    BOT_QWEN, BOT_DEEPSEEK, BOT_GPTOSS,
    BOT_CLAUDE_HAIKU, BOT_CLAUDE_SONNET, BOT_CLAUDE_OPUS,
)
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _env_text(key: str, default: str) -> str:
    raw = os.getenv(key)
    if raw is None:
        return default
    return str(raw).strip() or default


async def _safe_notify(notify_func: Optional[Callable], msg: str) -> None:
    """Send notification, silently log on failure."""
    if notify_func:
        try:
            await notify_func(msg)
        except Exception as e:
            logger.debug("[TeamVote] notify failed: %s", msg[:80])


def _render_vote_progress(symbol: str, votes: list, total: int = 6, phase: str = "") -> str:
    """渲染实时投票进度 — 搬运自 lobe-chat 的进度可视化思路
    
    让用户在等待时看到每个 AI 的投票实时出现，
    而不是 30-60 秒的静默等待。
    """
    vote_icons = {"BUY": "🟢", "HOLD": "🟡", "SKIP": "🔴"}
    pending_icon = "⏳"
    
    lines = [f"🗳 {symbol} AI 团队投票中"]
    lines.append("───────────────────")
    
    # 已完成的投票
    for v in votes:
        icon = vote_icons.get(v.vote, "❓")
        conf_bar = "█" * (v.confidence // 2) + "░" * (5 - v.confidence // 2)
        lines.append(f"{icon} {v.role}: {v.vote} [{conf_bar}] {v.confidence}/10")
    
    # 待投票的占位
    remaining = total - len(votes)
    for _ in range(remaining):
        lines.append(f"{pending_icon} 等待投票...")
    
    # 进度条
    pct = len(votes) / total
    bar_len = 20
    filled = int(pct * bar_len)
    bar = "▓" * filled + "░" * (bar_len - filled)
    lines.append(f"\n[{bar}] {len(votes)}/{total}")
    
    if phase:
        lines.append(f"📍 {phase}")
    
    return "\n".join(lines)


@dataclass
class BotVote:
    """单个Bot的投票"""
    bot_id: str
    bot_name: str
    role: str
    vote: str  # BUY / HOLD / SKIP
    confidence: int  # 1-10
    reasoning: str  # 简短理由
    entry_price: float = 0
    stop_loss: float = 0
    take_profit: float = 0


@dataclass
class VoteResult:
    """团队投票结果"""
    symbol: str
    votes: List[BotVote] = field(default_factory=list)
    decision: str = "HOLD"  # BUY / HOLD
    buy_count: int = 0
    hold_count: int = 0
    skip_count: int = 0
    vetoed: bool = False
    veto_reason: str = ""
    avg_confidence: float = 0
    avg_entry: float = 0
    avg_stop: float = 0
    avg_target: float = 0
    summary: str = ""
    data_completeness: float = 0
    used_data: List[str] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)
    price: float = 0
    change_pct: float = 0
    trend: str = ""
    signal_cn: str = ""
    support: float = 0
    resistance: float = 0
    vol_ratio: float = 0
    rsi6: float = 0
    rsi14: float = 0
    divergence: float = 0.0        # 信心分标准差（分歧度）
    is_high_divergence: bool = False  # 分歧度 > 2.5 时为 True

    def format_telegram(self) -> str:
        """格式化为 Telegram 完整流程报告（Full 模式）"""
        from src.utils import now_et
        now_text = now_et().strftime("%Y-%m-%d %H:%M ET")
        confidence_10 = self.avg_confidence * 10

        stop_pct = 0.0
        risk_reward = 0.0
        if self.avg_entry > 0 and self.avg_stop > 0:
            stop_pct = abs(self.avg_entry - self.avg_stop) / self.avg_entry * 100
        if self.avg_entry > self.avg_stop and self.avg_target > self.avg_entry:
            risk_reward = (self.avg_target - self.avg_entry) / (self.avg_entry - self.avg_stop)

        gate_notes: List[str] = []
        gate_ok = True
        if self.decision != "BUY":
            gate_ok = False
            gate_notes.append("当前结论非 BUY，风险闸门未放行新仓")
        if stop_pct > 0 and stop_pct > 3.2:
            gate_ok = False
            gate_notes.append(f"止损距离 {stop_pct:.2f}% 偏大")
        if risk_reward > 0 and risk_reward < 2.0:
            gate_ok = False
            gate_notes.append(f"风险收益比 {risk_reward:.2f}:1 低于 2.0:1")
        if self.vetoed:
            gate_ok = False
            gate_notes.append(self.veto_reason)
        if not gate_notes:
            gate_notes.append("风控与共识条件通过")

        used = "、".join(self.used_data) if self.used_data else "无"
        missing = "、".join(self.missing_data) if self.missing_data else "无"
        price_line = f"${self.price:.2f} / {self.change_pct:+.2f}%" if self.price > 0 else "数据缺失"

        lines = [
            f"[{self.symbol}] 完整交易流程报告",
            f"时间: {now_text}",
            "",
            "A. 最终裁决",
            f"- 动作: {self.decision} | 置信度: {confidence_10:.1f}/10",
            f"- 投票统计: BUY {self.buy_count} | HOLD {self.hold_count} | SKIP {self.skip_count}",
            f"- 结论备注: {self.veto_reason if self.veto_reason else '无否决'}",
            "",
            "B. 数据完整性审计",
            f"- 现价/涨跌: {price_line}",
            f"- 已使用数据: {used}",
            f"- 缺失数据: {missing}",
            f"- 完整度: {self.data_completeness:.0%}",
            "",
            "C. 多模型投票明细",
        ]

        for i, vote in enumerate(self.votes, start=1):
            lines.append(f"{i}) {vote.role}: {vote.vote} ({vote.confidence}/10)")
            lines.append(f"   理由: {vote.reasoning}")

        # 共识度/分歧度可视化
        if self.divergence > 0:
            consensus_pct = max(0, min(100, int(100 - self.divergence * 12)))
            filled = consensus_pct // 20
            dots = "●" * filled + "○" * (5 - filled)
            lines.append(f"\n🎯 共识度: {dots} {consensus_pct}% (σ={self.divergence:.1f})")
            if self.is_high_divergence:
                lines.append(f"⚠️ 分歧警告: 信心分标准差 {self.divergence:.1f} (>2.5)，AI 团队意见严重分化")

        lines.extend([
            "",
            "D. 风险闸门",
            f"- 闸门状态: {'通过' if gate_ok else '未通过'}",
            f"- 止损距离: {f'{stop_pct:.2f}%' if stop_pct > 0 else '待定'}",
            f"- 风险收益比: {f'{risk_reward:.2f}:1' if risk_reward > 0 else '待定'}",
            f"- 风险备注: {'；'.join(gate_notes)}",
            "",
            "E. 执行计划",
        ])

        if self.decision == "BUY" and self.avg_entry > 0:
            lines.extend([
                f"- 入场价: ${self.avg_entry:.2f}",
                f"- 止损价: ${self.avg_stop:.2f}" if self.avg_stop > 0 else "- 止损价: 待定",
                f"- 目标价: ${self.avg_target:.2f}" if self.avg_target > 0 else "- 目标价: 待定",
                "- 执行方式: 分批入场（突破确认 + 回踩确认）",
            ])
        else:
            trigger_parts: List[str] = []
            if self.resistance > 0:
                trigger_parts.append(f"放量站稳 ${self.resistance:.2f}")
            if self.vol_ratio > 0:
                trigger_parts.append("量比提升并持续")
            if not trigger_parts:
                trigger_parts.append("趋势与量能双确认")
            lines.extend([
                "- 当前动作: 观望，不开新仓",
                f"- 触发条件: {' + '.join(trigger_parts)}",
                "- 触发前动作: 仅跟踪，不下单",
            ])

        lines.extend([
            "",
            "F. 失效条件与应急",
            f"- 失效条件: {f'跌破 ${self.support:.2f} 且量价转弱' if self.support > 0 else '趋势走坏或出现放量反向'}",
            "- 应急动作: 取消挂单 -> 降低风险暴露 -> 等下一窗口",
            "",
            "G. 复盘记录",
            f"- 本次结论: {self.decision}",
            "- 下次检查点: 下一根 4H 收线后复评",
        ])
        return "\n".join(lines)


# 每位Bot的投票提示模板 — 单一事实源: config/prompts.py
VOTE_PROMPTS = INVEST_VOTE_PROMPTS

# 投票顺序: 雷达->宏观->图表->风控->指挥官->首席策略师
VOTE_ORDER = [BOT_CLAUDE_HAIKU, BOT_QWEN, BOT_GPTOSS, BOT_DEEPSEEK, BOT_CLAUDE_SONNET, BOT_CLAUDE_OPUS]


def _parse_vote(text: str, bot_id: str, bot_name: str, role: str) -> BotVote:
    """从 AI 回复中解析投票，优先 JSON，失败时做稳健回退。"""

    def _normalize_vote(raw: object) -> str:
        token = str(raw or "").upper().strip()
        if token in ("BUY", "HOLD", "SKIP"):
            return token
        return "HOLD"

    def _clean_reasoning(raw: object) -> str:
        text_raw = str(raw or "")
        text_raw = re.sub(r"```[\\s\\S]*?```", " ", text_raw)
        text_raw = re.sub(r"\{[\s\S]{30,}\}", " ", text_raw)
        text_raw = re.sub(r"\s+", " ", text_raw).strip().strip('"\'')
        if not text_raw:
            return "未提供明确理由"
        return text_raw[:160]

    def _extract_json_with_vote(raw_text: str) -> Optional[dict]:
        candidates: List[str] = []
        fenced = re.findall(r"```(?:json|JSON)?\s*([\s\S]*?)```", raw_text)
        candidates.extend([c.strip() for c in fenced if c and c.strip()])
        candidates.append(raw_text.strip())

        def _try_json(candidate: str) -> Optional[dict]:
            if not candidate:
                return None
            from json_repair import loads as jloads
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    data = jloads(candidate)
                    if isinstance(data, dict) and "vote" in data:
                        return data
                except Exception as e:  # noqa: F841
                    return None
            return None

        for candidate in candidates:
            parsed = _try_json(candidate)
            if parsed is not None:
                return parsed

            starts = [m.start() for m in re.finditer(r"\{", candidate)]
            for start in starts:
                depth = 0
                in_string = False
                escaped = False
                for idx in range(start, len(candidate)):
                    ch = candidate[idx]
                    if in_string:
                        if escaped:
                            escaped = False
                        elif ch == "\\":
                            escaped = True
                        elif ch == '"':
                            in_string = False
                        continue
                    if ch == '"':
                        in_string = True
                        continue
                    if ch == "{":
                        depth += 1
                        continue
                    if ch == "}":
                        depth -= 1
                        if depth == 0:
                            snippet = candidate[start:idx + 1]
                            if '"vote"' not in snippet and "'vote'" not in snippet:
                                break
                            parsed = _try_json(snippet)
                            if parsed is not None:
                                return parsed
                            break
        return None

    raw = text or ""
    data = _extract_json_with_vote(raw)
    if data is None:
        vote_match = re.search(r"['\"]?vote['\"]?\s*[:：]\s*['\"]?(BUY|HOLD|SKIP)", raw, re.IGNORECASE)
        conf_match = re.search(r"['\"]?confidence['\"]?\s*[:：]\s*(\d{1,2})", raw, re.IGNORECASE)
        reason_match = re.search(r"['\"]?reasoning['\"]?\s*[:：]\s*['\"]([^'\"]{1,220})", raw, re.IGNORECASE)
        data = {
            "vote": vote_match.group(1).upper() if vote_match else None,
            "confidence": int(conf_match.group(1)) if conf_match else 5,
            "reasoning": reason_match.group(1) if reason_match else raw,
            "entry_price": 0,
            "stop_loss": 0,
            "take_profit": 0,
        }

    vote = _normalize_vote(data.get("vote"))
    if vote == "HOLD":
        text_lower = raw.lower()
        if any(w in text_lower for w in ["skip", "跳过", "放弃", "不推荐"]):
            vote = "SKIP"
        elif any(w in text_lower for w in ["hold", "观望", "等待", "暂不", "不新开仓"]):
            vote = "HOLD"
        elif any(w in text_lower for w in ["buy", "买入", "做多", "long"]):
            vote = "BUY"

    confidence = data.get("confidence", 5)
    try:
        confidence = int(confidence)
    except (TypeError, ValueError) as e:  # noqa: F841
        confidence = 5

    return BotVote(
        bot_id=bot_id,
        bot_name=bot_name,
        role=role,
        vote=vote,
        confidence=max(1, min(10, confidence)),
        reasoning=_clean_reasoning(data.get("reasoning", "")),
        entry_price=safe_float(str(data.get("entry_price", 0))),
        stop_loss=safe_float(str(data.get("stop_loss", 0))),
        take_profit=safe_float(str(data.get("take_profit", 0))),
    )


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _to_float(value: Any) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError) as e:  # noqa: F841
        return 0.0


def _build_data_audit(analysis: dict) -> Tuple[List[str], List[str], float]:
    if not isinstance(analysis, dict):
        return [], ["技术数据"], 0.0

    ind = analysis.get("indicators", {}) if isinstance(analysis.get("indicators"), dict) else {}
    sig = analysis.get("signal", {}) if isinstance(analysis.get("signal"), dict) else {}
    sr = analysis.get("support_resistance", {}) if isinstance(analysis.get("support_resistance"), dict) else {}

    checks = [
        ("现价", analysis.get("price")),
        ("涨跌幅", analysis.get("change_pct")),
        ("RSI6", ind.get("rsi_6")),
        ("RSI14", ind.get("rsi_14")),
        ("MACD", ind.get("macd")),
        ("Signal", ind.get("macd_signal")),
        ("趋势", ind.get("trend")),
        ("量比", ind.get("vol_ratio")),
        ("ATR%", ind.get("atr_pct")),
        ("ADX", ind.get("adx")),
        ("信号评分", sig.get("score")),
        ("信号标签", sig.get("signal_cn")),
        ("支撑位", (sr.get("supports") or [None])[0] if isinstance(sr.get("supports"), list) else None),
        ("阻力位", (sr.get("resistances") or [None])[0] if isinstance(sr.get("resistances"), list) else None),
    ]

    used = [name for name, value in checks if _has_value(value)]
    missing = [name for name, value in checks if not _has_value(value)]
    completeness = len(used) / len(checks) if checks else 0.0
    return used, missing, completeness


def _format_ta_summary(analysis: dict) -> str:
    """将技术分析数据格式化为简洁摘要"""
    if not analysis or not isinstance(analysis, dict):
        return "(无技术数据)"

    lines = []
    lines.append(f"标的: {analysis.get('symbol', '?')} ${analysis.get('price', 0):.2f}")
    lines.append(f"涨跌: {analysis.get('change_pct', 0):+.2f}%")

    ind = analysis.get("indicators", {})
    if ind:
        lines.append(f"RSI6={ind.get('rsi_6', 0):.0f} RSI14={ind.get('rsi_14', 0):.0f}")
        lines.append(f"MACD={ind.get('macd', 0):.3f} Signal={ind.get('macd_signal', 0):.3f}")
        lines.append(f"趋势={ind.get('trend', '?')} 量比={ind.get('vol_ratio', 0):.1f}x")
        lines.append(f"ATR%={ind.get('atr_pct', 0):.2f}%")
        adx = ind.get('adx', 0)
        if adx > 0:
            adx_label = "强趋势" if adx >= 40 else "趋势" if adx >= 25 else "弱趋势" if adx >= 20 else "震荡"
            lines.append(f"ADX={adx:.0f}({adx_label}) +DI={ind.get('adx_pos', 0):.0f} -DI={ind.get('adx_neg', 0):.0f}")
        # OBV 方向
        obv_rising = ind.get('obv_rising')
        if obv_rising is not None:
            lines.append(f"OBV方向={'上升(量价配合)' if obv_rising else '下降(量价背离)'}")

    sig = analysis.get("signal", {})
    if sig:
        lines.append(f"信号: {sig.get('signal_cn', '?')} 评分={sig.get('score', 0):+d}")

    sr = analysis.get("support_resistance", {})
    if sr:
        sups = sr.get("supports", [])
        ress = sr.get("resistances", [])
        if sups:
            lines.append(f"支撑: {sups[0]}")
        if ress:
            lines.append(f"阻力: {ress[0]}")

    return "\n".join(lines)


async def run_team_vote(
    symbol: str,
    analysis: dict,
    api_callers: Dict[str, Callable],
    notify_func: Optional[Callable] = None,
    timeout_per_bot: float = 60,
    account_context: str = "",
    vote_history: Optional[Dict[str, Dict]] = None,
    progress_func: Optional[Callable] = None,
) -> VoteResult:
    """
    对单个标的运行6人团队投票。

    Args:
        symbol: 标的代码
        analysis: 技术分析数据 (from get_full_analysis)
        api_callers: {bot_id: async callable(chat_id, prompt)} 映射
        notify_func: Telegram通知回调
        timeout_per_bot: 每个Bot的超时秒数
        vote_history: {bot_id: {"total": N, "correct": N, "accuracy": float}} 历史准确率
        progress_func: 实时进度回调 async (text: str) -> None，用于编辑进度消息

    Returns:
        VoteResult 投票结果
    """
    result = VoteResult(symbol=symbol)
    analysis_data = analysis if isinstance(analysis, dict) else {}
    ind = analysis_data.get("indicators", {}) if isinstance(analysis_data.get("indicators"), dict) else {}
    sig = analysis_data.get("signal", {}) if isinstance(analysis_data.get("signal"), dict) else {}
    sr = analysis_data.get("support_resistance", {}) if isinstance(analysis_data.get("support_resistance"), dict) else {}
    supports = sr.get("supports") if isinstance(sr.get("supports"), list) else []
    resistances = sr.get("resistances") if isinstance(sr.get("resistances"), list) else []
    used, missing, completeness = _build_data_audit(analysis_data)
    result.used_data = used
    result.missing_data = missing
    result.data_completeness = completeness
    result.price = _to_float(analysis_data.get("price", 0))
    result.change_pct = _to_float(analysis_data.get("change_pct", 0))
    result.trend = str(ind.get("trend", "") or "")
    result.signal_cn = str(sig.get("signal_cn", "") or "")
    result.support = _to_float(supports[0]) if supports else 0.0
    result.resistance = _to_float(resistances[0]) if resistances else 0.0
    result.vol_ratio = _to_float(ind.get("vol_ratio", 0))
    result.rsi6 = _to_float(ind.get("rsi_6", 0))
    result.rsi14 = _to_float(ind.get("rsi_14", 0))

    ta_summary = _format_ta_summary(analysis_data)
    account_ctx = account_context or "(无账户信息)"
    vote_hist = vote_history or {}

    # 构建历史准确率提示（让AI自我校准）
    def _history_hint(bot_id: str) -> str:
        h = vote_hist.get(bot_id)
        if not h or h.get("total", 0) < 3:
            return ""
        return (
            f"\n[你的历史表现: {h['total']}次投票, 准确率{h.get('accuracy', 0):.0f}%, "
            f"请据此校准你的置信度]\n"
        )

    # --- 阶段1: 前4个分析师并行投票（雷达/宏观/图表/风控）---
    parallel_bots = [b for b in VOTE_ORDER if b not in (BOT_CLAUDE_SONNET, BOT_CLAUDE_OPUS)]

    async def _call_bot(bot_id: str) -> BotVote:
        prompt_cfg = VOTE_PROMPTS.get(bot_id)
        if not prompt_cfg:
            return BotVote(bot_id=bot_id, bot_name=bot_id, role="?",
                           vote="HOLD", confidence=1, reasoning="无配置")
        caller = api_callers.get(bot_id)
        if not caller:
            logger.warning("[TeamVote] %s 无API caller，跳过", bot_id)
            return BotVote(bot_id=bot_id, bot_name=bot_id, role=prompt_cfg["role"],
                           vote="HOLD", confidence=1, reasoning="无API caller")
        role = prompt_cfg["role"]
        prompt = prompt_cfg["prompt"].format(
            symbol=symbol, ta_summary=ta_summary,
            previous_votes="(并行投票，无前序结果)",
            account_context=account_ctx,
        )
        # 注入历史准确率提示
        hint = _history_hint(bot_id)
        if hint:
            prompt = hint + prompt
        # 带重试的投票调用（防 Kiro 网关断连）
        max_attempts = 2
        last_err = ""
        for attempt in range(max_attempts):
            try:
                response = await asyncio.wait_for(
                    caller(-999, prompt), timeout=timeout_per_bot,
                )
                return _parse_vote(response, bot_id, bot_id, role)
            except asyncio.TimeoutError as e:
                last_err = "回复超时"
                logger.warning("[TeamVote] %s 超时(%ds) [%d/%d]", bot_id, timeout_per_bot, attempt + 1, max_attempts)
            except Exception as e:
                last_err = str(e)
                logger.warning("[TeamVote] %s 失败 [%d/%d]: %s", bot_id, attempt + 1, max_attempts, e)
            if attempt < max_attempts - 1:
                await asyncio.sleep(2)
        return BotVote(bot_id=bot_id, bot_name=bot_id, role=role,
                       vote="HOLD", confidence=1, reasoning=f"重试{max_attempts}次失败: {last_err}")

    # 并行调用前4个分析师（错开0.5s减轻网关压力）
    async def _staggered_call(bot_id: str, delay: float) -> BotVote:
        if delay > 0:
            await asyncio.sleep(delay)
        return await _call_bot(bot_id)

    parallel_votes = await asyncio.gather(
        *[_staggered_call(bid, i * 0.5) for i, bid in enumerate(parallel_bots)],
        return_exceptions=True,
    )

    previous_votes_text = ""
    for bid, vote_or_exc in zip(parallel_bots, parallel_votes):
        vote: BotVote
        if isinstance(vote_or_exc, BaseException):
            prompt_cfg = VOTE_PROMPTS.get(bid, {})
            vote = BotVote(bot_id=bid, bot_name=bid, role=prompt_cfg.get("role", "?"),
                           vote="HOLD", confidence=1, reasoning=f"异常: {vote_or_exc}")
        elif isinstance(vote_or_exc, BotVote):
            vote = vote_or_exc
        else:
            vote = BotVote(bot_id=bid, bot_name=bid, role="?",
                           vote="HOLD", confidence=1, reasoning="未知投票结果类型")
        result.votes.append(vote)
        vote_icon = {"BUY": "+", "HOLD": "=", "SKIP": "-"}.get(vote.vote, "?")
        previous_votes_text += f"[{vote_icon}] {vote.role}: {vote.vote}({vote.confidence}/10) {vote.reasoning}\n"

    # 实时进度更新：阶段1完成
    await _safe_notify(progress_func,
        _render_vote_progress(symbol, result.votes, 6, "阶段1完成 · 指挥官投票中..."))

    # --- 阶段2: 指挥官串行投票（看到前4人结果）---
    # 构建交易教训（闭环学习 — 让高级 AI 看到近期失败模式）
    trade_lessons = ""
    try:
        from src.trading_journal import journal as tj
        if tj and hasattr(tj, 'get_latest_review'):
            latest_review = tj.get_latest_review("daily")
            if latest_review and latest_review.get("lessons_learned"):
                trade_lessons = "[近期交易教训]\n" + str(latest_review["lessons_learned"])[:300]
    except Exception as e:
        logger.debug("Silenced exception", exc_info=True)

    commander_id = BOT_CLAUDE_SONNET
    prompt_cfg = VOTE_PROMPTS.get(commander_id)
    caller = api_callers.get(commander_id)
    if prompt_cfg and caller:
        role = prompt_cfg["role"]
        prompt = prompt_cfg["prompt"].format(
            symbol=symbol, ta_summary=ta_summary,
            previous_votes=previous_votes_text,
            account_context=account_ctx,
            trade_lessons=trade_lessons,
        )
        commander_vote_result = BotVote(
            bot_id=commander_id,
            bot_name=commander_id,
            role=role,
            vote="HOLD",
            confidence=1,
            reasoning="重试2次失败",
        )
        for _attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    caller(-999, prompt), timeout=timeout_per_bot,
                )
                commander_vote_result = _parse_vote(response, commander_id, commander_id, role)
                break
            except asyncio.TimeoutError as e:
                logger.warning("[TeamVote] %s 超时 [%d/2]", commander_id, _attempt + 1)
            except Exception as e:
                logger.warning("[TeamVote] %s 失败 [%d/2]: %s", commander_id, _attempt + 1, e)
            if _attempt == 0:
                await asyncio.sleep(2)
        result.votes.append(commander_vote_result)

    # 实时进度更新：阶段2完成
    await _safe_notify(progress_func,
        _render_vote_progress(symbol, result.votes, 6, "阶段2完成 · 首席策略师投票中..."))

    # --- 阶段3: 首席策略师串行投票（看到前5人结果）---
    # 更新 previous_votes_text，加入指挥官的投票
    commander_vote = next((v for v in result.votes if v.bot_id == BOT_CLAUDE_SONNET), None)
    if commander_vote:
        vote_icon = {"BUY": "+", "HOLD": "=", "SKIP": "-"}.get(commander_vote.vote, "?")
        previous_votes_text += f"[{vote_icon}] {commander_vote.role}: {commander_vote.vote}({commander_vote.confidence}/10) {commander_vote.reasoning}\n"

    strategist_id = BOT_CLAUDE_OPUS
    prompt_cfg = VOTE_PROMPTS.get(strategist_id)
    caller = api_callers.get(strategist_id)
    if prompt_cfg and caller:
        role = prompt_cfg["role"]
        prompt = prompt_cfg["prompt"].format(
            symbol=symbol, ta_summary=ta_summary,
            previous_votes=previous_votes_text,
            account_context=account_ctx,
            trade_lessons=trade_lessons,
        )
        strategist_vote_result = BotVote(
            bot_id=strategist_id,
            bot_name=strategist_id,
            role=role,
            vote="HOLD",
            confidence=1,
            reasoning="重试2次失败",
        )
        for _attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    caller(-999, prompt), timeout=timeout_per_bot,
                )
                strategist_vote_result = _parse_vote(response, strategist_id, strategist_id, role)
                break
            except asyncio.TimeoutError as e:
                logger.warning("[TeamVote] %s 超时 [%d/2]", strategist_id, _attempt + 1)
            except Exception as e:
                logger.warning("[TeamVote] %s 失败 [%d/2]: %s", strategist_id, _attempt + 1, e)
            if _attempt == 0:
                await asyncio.sleep(2)
        result.votes.append(strategist_vote_result)

    # 实时进度更新：全部投票完成
    await _safe_notify(progress_func,
        _render_vote_progress(symbol, result.votes, 6, "投票完成 · 统计中..."))

    # 统计投票
    result.buy_count = sum(1 for v in result.votes if v.vote == "BUY")
    result.hold_count = sum(1 for v in result.votes if v.vote == "HOLD")
    result.skip_count = sum(1 for v in result.votes if v.vote == "SKIP")

    # 计算信心分标准差（分歧度）— prompts.py L238 规则的代码实现
    all_confidences = [v.confidence for v in result.votes if v.confidence > 0]
    result.divergence = statistics.stdev(all_confidences) if len(all_confidences) > 1 else 0.0
    result.is_high_divergence = result.divergence > 2.5

    min_buy_votes = max(2, env_int("TEAM_MIN_BUY_VOTES", 3))
    min_avg_buy_conf = max(1.0, min(10.0, env_float("TEAM_MIN_AVG_BUY_CONF", 5.5)))
    veto_mode = _env_text("TEAM_VETO_MODE", "dual").lower()  # off / single / dual

    # 风控官 / 首席策略师 否决规则（可配置）
    risk_vote = next((v for v in result.votes if v.bot_id == BOT_DEEPSEEK), None)
    strategist_vote = next((v for v in result.votes if v.bot_id == BOT_CLAUDE_OPUS), None)
    risk_skip = bool(risk_vote and risk_vote.vote == "SKIP")
    strategist_skip = bool(strategist_vote and strategist_vote.vote == "SKIP")

    if veto_mode == "single" and (risk_skip or strategist_skip):
        result.vetoed = True
        if risk_skip and risk_vote is not None:
            result.veto_reason = f"风控铁闸否决: {risk_vote.reasoning}"
        elif strategist_vote is not None:
            result.veto_reason = f"首席策略师否决: {strategist_vote.reasoning}"
        else:
            result.veto_reason = "否决（详情缺失）"
        result.decision = "HOLD"
    elif veto_mode == "dual" and risk_skip and strategist_skip:
        result.vetoed = True
        result.veto_reason = "双重否决: 风控铁闸与首席策略师一致反对"
        result.decision = "HOLD"
    elif result.buy_count >= min_buy_votes:
        # 计算 BUY 投票者的平均置信度
        buy_votes_for_conf = [v for v in result.votes if v.vote == "BUY"]
        avg_buy_conf = sum(v.confidence for v in buy_votes_for_conf) / len(buy_votes_for_conf) if buy_votes_for_conf else 0
        if avg_buy_conf >= min_avg_buy_conf:
            # 高分歧降级保护：边缘通过 + 团队严重分化 → 保守观望
            if result.is_high_divergence and result.buy_count == min_buy_votes:
                result.decision = "HOLD"
                result.veto_reason = f"团队分歧过大 (σ={result.divergence:.1f}), 保守观望"
            else:
                result.decision = "BUY"
        else:
            result.decision = "HOLD"
            result.veto_reason = (
                "BUY票数达标但平均置信度不足(%.1f/10 < %.1f)"
                % (avg_buy_conf, min_avg_buy_conf)
            )
    else:
        result.decision = "HOLD"

    # 计算加权平均
    buy_votes = [v for v in result.votes if v.vote == "BUY"]
    if buy_votes:
        result.avg_confidence = sum(v.confidence for v in buy_votes) / (len(buy_votes) * 10)

        # 只用提供了有效价格的投票者计算加权平均（避免分母稀释）
        entry_votes = [v for v in buy_votes if v.entry_price > 0]
        stop_votes = [v for v in buy_votes if v.stop_loss > 0]
        target_votes = [v for v in buy_votes if v.take_profit > 0]

        if entry_votes:
            w = sum(v.confidence for v in entry_votes)
            result.avg_entry = sum(v.entry_price * v.confidence for v in entry_votes) / w
        if stop_votes:
            w = sum(v.confidence for v in stop_votes)
            result.avg_stop = sum(v.stop_loss * v.confidence for v in stop_votes) / w
        if target_votes:
            w = sum(v.confidence for v in target_votes)
            result.avg_target = sum(v.take_profit * v.confidence for v in target_votes) / w
    else:
        result.avg_confidence = sum(v.confidence for v in result.votes) / (len(result.votes) * 10) if result.votes else 0

    main_reasons = [v.reasoning for v in result.votes if v.vote == result.decision and v.reasoning]
    if not main_reasons and result.votes:
        main_reasons = [result.votes[0].reasoning]
    brief_reason = main_reasons[0][:40] if main_reasons else ""

    result.summary = (
        f"{symbol}: {result.decision} "
        f"(BUY:{result.buy_count} HOLD:{result.hold_count} SKIP:{result.skip_count}) "
        f"置信度{result.avg_confidence:.0%} σ={result.divergence:.1f}"
    )
    if brief_reason:
        result.summary += f" | {brief_reason}"
    if result.vetoed:
        result.summary += f" [否决: {result.veto_reason}]"

    return result


async def run_team_vote_batch(
    candidates: List[dict],
    analyses: Dict[str, dict],
    api_callers: Dict[str, Callable],
    notify_func: Optional[Callable] = None,
    max_candidates: int = 5,
    account_context: str = "",
    vote_history: Optional[Dict[str, Dict]] = None,
    progress_func: Optional[Callable] = None,
) -> List[VoteResult]:
    """
    对多个候选标的批量运行团队投票。

    Args:
        candidates: 候选标的列表 (from _filter_candidates)
        analyses: {symbol: analysis_data} 映射
        api_callers: {bot_id: async callable} 映射
        notify_func: Telegram通知回调
        max_candidates: 最多分析几个候选
        vote_history: {bot_id: {"total": N, "correct": N, "accuracy": float}} 历史准确率
        progress_func: 实时进度回调

    Returns:
        按 buy_count 降序排列的 VoteResult 列表
    """
    results = []

    for i, candidate in enumerate(candidates[:max_candidates]):
        symbol = candidate.get("symbol", "")
        analysis = analyses.get(symbol, {})

        await _safe_notify(notify_func,
            f"\n-- 分析候选 {i+1}/{min(len(candidates), max_candidates)}: {symbol} --")

        vote_result = await run_team_vote(
            symbol=symbol,
            analysis=analysis,
            api_callers=api_callers,
            notify_func=notify_func,
            account_context=account_context,
            vote_history=vote_history,
            progress_func=progress_func,
        )
        results.append(vote_result)

        # 播报投票结果
        await _safe_notify(notify_func, vote_result.format_telegram())

    # 按 buy_count 降序，同票数按 avg_confidence 降序
    results.sort(key=lambda r: (r.buy_count, r.avg_confidence), reverse=True)
    return results
