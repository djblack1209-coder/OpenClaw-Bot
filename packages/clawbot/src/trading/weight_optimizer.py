"""
Trading — 投票权重优化器 (基于 Optuna 11k⭐)

用回测数据自动优化 AI 团队投票权重:
- 每个 AI 分析师的投票权重
- 最低买入票数阈值
- 最低平均置信度阈值
- 否决权模式

核心思路: 用历史投票记录 + 实际交易结果，
通过贝叶斯优化找到最优权重组合。
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# AI 团队成员 ID（与 ai_team_voter.py 对齐）
TEAM_MEMBERS = [
    "market_radar",    # Claude Haiku — 快速市场扫描
    "macro_hunter",    # Qwen — 宏观面分析
    "chart_sniper",    # GPT — 技术图表
    "risk_gate",       # DeepSeek — 风控把关
    "commander",       # Claude Sonnet — 综合决策
    "chief_strategist", # Claude Opus — 首席策略师
]

DEFAULT_WEIGHTS = {m: 1.0 for m in TEAM_MEMBERS}
DEFAULT_WEIGHTS["chief_strategist"] = 1.5  # 首席策略师默认更高权重
DEFAULT_WEIGHTS["risk_gate"] = 1.2         # 风控稍高权重


@dataclass
class OptimizationResult:
    """优化结果"""
    best_weights: Dict[str, float]
    best_min_votes: int
    best_min_confidence: float
    best_veto_mode: str
    objective_value: float  # 优化目标值（如 Sharpe ratio）
    n_trials: int
    study_name: str = ""


@dataclass
class VoteRecord:
    """单次投票记录（用于优化）"""
    symbol: str
    timestamp: str
    votes: Dict[str, Dict]  # member_id -> {action, confidence, entry, stop, target}
    final_decision: str     # BUY / HOLD / SELL
    actual_pnl_pct: float = 0.0  # 实际收益率（回测或实盘）
    actual_outcome: str = ""     # win / loss / pending


def _compute_weighted_decision(
    votes: Dict[str, Dict],
    weights: Dict[str, float],
    min_buy_votes: int = 3,
    min_avg_confidence: float = 5.5,
    veto_mode: str = "off",
) -> Tuple[str, float]:
    """用给定权重重新计算投票决策"""
    buy_weighted_sum = 0.0
    total_weight = 0.0
    buy_count = 0
    buy_confidences = []
    veto_triggered = False

    for member_id, vote in votes.items():
        action = str(vote.get("action", "HOLD")).upper()
        confidence = float(vote.get("confidence", 5))
        w = weights.get(member_id, 1.0)
        total_weight += w

        if action == "BUY":
            buy_count += 1
            buy_weighted_sum += confidence * w
            buy_confidences.append(confidence)
        elif action == "SELL" or action == "SKIP":
            # 否决权检查
            if veto_mode == "single" and member_id in ("risk_gate", "chief_strategist"):
                if confidence >= 7:
                    veto_triggered = True
            elif veto_mode == "dual":
                pass  # 需要两个否决才生效，简化处理

    if veto_triggered:
        return "HOLD", 0.0

    avg_confidence = sum(buy_confidences) / len(buy_confidences) if buy_confidences else 0
    weighted_avg = buy_weighted_sum / total_weight if total_weight > 0 else 0

    if buy_count >= min_buy_votes and avg_confidence >= min_avg_confidence:
        return "BUY", weighted_avg
    return "HOLD", weighted_avg


def optimize_weights(
    vote_records: List[VoteRecord],
    n_trials: int = 100,
    objective: str = "sharpe",
    study_name: str = "clawbot_vote_weights",
) -> OptimizationResult:
    """
    使用 Optuna 优化 AI 团队投票权重。

    Args:
        vote_records: 历史投票记录（含实际收益）
        n_trials: 优化迭代次数
        objective: 优化目标 (sharpe / profit_factor / win_rate)
        study_name: Optuna study 名称
    """
    if not vote_records:
        logger.warning("[WeightOptimizer] 无投票记录，返回默认权重")
        return OptimizationResult(
            best_weights=DEFAULT_WEIGHTS.copy(),
            best_min_votes=3,
            best_min_confidence=5.5,
            best_veto_mode="off",
            objective_value=0.0,
            n_trials=0,
        )

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("[WeightOptimizer] Optuna 未安装，返回默认权重")
        return OptimizationResult(
            best_weights=DEFAULT_WEIGHTS.copy(),
            best_min_votes=3,
            best_min_confidence=5.5,
            best_veto_mode="off",
            objective_value=0.0,
            n_trials=0,
        )

    def _objective(trial):
        # 搜索空间: 每个成员的权重
        weights = {}
        for member in TEAM_MEMBERS:
            weights[member] = trial.suggest_float(f"w_{member}", 0.1, 3.0)

        min_votes = trial.suggest_int("min_buy_votes", 2, 5)
        min_conf = trial.suggest_float("min_avg_confidence", 4.0, 8.0)
        veto = trial.suggest_categorical("veto_mode", ["off", "single", "dual"])

        # 模拟: 用这组参数重新决策所有历史记录
        pnls = []
        wins = 0
        losses = 0

        for record in vote_records:
            decision, _ = _compute_weighted_decision(
                record.votes, weights, min_votes, min_conf, veto
            )
            if decision == "BUY":
                pnls.append(record.actual_pnl_pct)
                if record.actual_pnl_pct > 0:
                    wins += 1
                else:
                    losses += 1

        if not pnls:
            return -999.0  # 没有任何交易 = 最差

        # 计算目标值
        import statistics
        avg_pnl = statistics.mean(pnls)
        std_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 1.0

        if objective == "sharpe":
            return avg_pnl / max(std_pnl, 0.01)
        elif objective == "profit_factor":
            gross_profit = sum(p for p in pnls if p > 0)
            gross_loss = abs(sum(p for p in pnls if p < 0))
            return gross_profit / max(gross_loss, 0.01)
        elif objective == "win_rate":
            return wins / max(wins + losses, 1)
        else:
            return avg_pnl

    study = optuna.create_study(
        study_name=study_name,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(_objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    best_weights = {m: best.get(f"w_{m}", 1.0) for m in TEAM_MEMBERS}

    result = OptimizationResult(
        best_weights=best_weights,
        best_min_votes=best.get("min_buy_votes", 3),
        best_min_confidence=best.get("min_avg_confidence", 5.5),
        best_veto_mode=best.get("veto_mode", "off"),
        objective_value=study.best_value,
        n_trials=n_trials,
        study_name=study_name,
    )

    logger.info(
        f"[WeightOptimizer] 优化完成: {objective}={result.objective_value:.3f}, "
        f"trials={n_trials}, weights={best_weights}"
    )
    return result


def save_weights(result: OptimizationResult, path: str = None):
    """保存优化结果到文件"""
    if not path:
        path = str(Path(__file__).parent.parent.parent / "data" / "vote_weights.json")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "weights": result.best_weights,
        "min_buy_votes": result.best_min_votes,
        "min_avg_confidence": result.best_min_confidence,
        "veto_mode": result.best_veto_mode,
        "objective_value": result.objective_value,
        "n_trials": result.n_trials,
    }
    Path(path).write_text(json.dumps(payload, indent=2))
    logger.info(f"[WeightOptimizer] 权重已保存到 {path}")


def load_weights(path: str = None) -> Dict[str, float]:
    """加载优化后的权重"""
    if not path:
        path = str(Path(__file__).parent.parent.parent / "data" / "vote_weights.json")
    try:
        payload = json.loads(Path(path).read_text())
        return payload.get("weights", DEFAULT_WEIGHTS.copy())
    except Exception as e:  # noqa: F841
        return DEFAULT_WEIGHTS.copy()
