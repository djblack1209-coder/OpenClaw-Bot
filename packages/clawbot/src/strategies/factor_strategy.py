"""
Alpha 因子 + ML 信号策略 — 搬运自 Qlib (Microsoft, 18k⭐, MIT)

核心搬运组件:
  - Alpha 因子库 — 简化自 qlib/data/factor/ 常用因子
  - LightGBM 信号模型 — 参考 qlib/model/LGBModel

架构适配:
  - 继承 BaseStrategy，实现 analyze(MarketData) -> TradeSignal
  - 训练好的模型缓存在 packages/clawbot/src/models/factor/
  - 缺依赖时 graceful degradation → 纯因子得分 (无 ML)

v1.0 — 2026-03-24
"""

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.strategy_engine import BaseStrategy, MarketData, SignalType, TradeSignal
from src.utils import now_et, scrub_secrets

logger = logging.getLogger(__name__)

# ============ 可选依赖检测 ============

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

HAS_JOBLIB = importlib.util.find_spec("joblib") is not None

# 模型缓存目录
MODEL_DIR = Path(__file__).parent.parent / "models" / "factor"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ============ 搬运自 Qlib: Alpha 因子库 ============

class AlphaFactors:
    """Alpha 因子计算器 — 简化自 Qlib data/factor

    因子列表 (16个经典因子):
      动量类: mom_5d, mom_10d, mom_20d, mom_60d
      均值回归: mean_reversion_5d, mean_reversion_20d
      波动率: volatility_5d, volatility_20d
      成交量: volume_ratio_5d, volume_ratio_20d, obv_slope
      技术面: rsi_14, macd_hist, bb_position
      价格形态: price_range, gap_ratio
    """

    @staticmethod
    def compute_all(df: pd.DataFrame) -> pd.DataFrame:
        """计算所有 Alpha 因子"""
        factors = pd.DataFrame(index=df.index)
        close = df["close"]
        volume = df.get("volume", pd.Series(1_000_000, index=df.index))
        high = df.get("high", close * 1.01)
        low = df.get("low", close * 0.99)
        open_ = df.get("open", close)

        # ---- 动量因子 ----
        factors["mom_5d"] = close.pct_change(5)
        factors["mom_10d"] = close.pct_change(10)
        factors["mom_20d"] = close.pct_change(20)
        factors["mom_60d"] = close.pct_change(60)

        # ---- 均值回归因子 ----
        ma5 = close.rolling(5, min_periods=1).mean()
        ma20 = close.rolling(20, min_periods=1).mean()
        factors["mean_reversion_5d"] = (close - ma5) / ma5
        factors["mean_reversion_20d"] = (close - ma20) / ma20

        # ---- 波动率因子 ----
        factors["volatility_5d"] = close.pct_change().rolling(5, min_periods=1).std()
        factors["volatility_20d"] = close.pct_change().rolling(20, min_periods=1).std()

        # ---- 成交量因子 ----
        avg_vol_5 = volume.rolling(5, min_periods=1).mean()
        avg_vol_20 = volume.rolling(20, min_periods=1).mean()
        factors["volume_ratio_5d"] = volume / avg_vol_5.replace(0, 1)
        factors["volume_ratio_20d"] = volume / avg_vol_20.replace(0, 1)

        # OBV 斜率
        obv = (np.sign(close.diff()) * volume).cumsum()
        factors["obv_slope"] = obv.rolling(10, min_periods=1).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) > 1 else 0,
            raw=False,
        )

        # ---- 技术面因子 ----
        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
        loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
        rs = gain / loss.replace(0, 1e-10)
        factors["rsi_14"] = (100 - 100 / (1 + rs)) / 100  # 归一化到 [0, 1]

        # MACD histogram
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line
        factors["macd_hist"] = macd_hist / close  # 归一化

        # 布林带位置 (%B)
        bb_mid = close.rolling(20, min_periods=1).mean()
        bb_std = close.rolling(20, min_periods=1).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = bb_upper - bb_lower
        factors["bb_position"] = (close - bb_lower) / bb_width.replace(0, 1)

        # ---- 价格形态因子 ----
        factors["price_range"] = (high - low) / close  # 日内振幅
        factors["gap_ratio"] = (open_ - close.shift(1)) / close.shift(1)  # 跳空比

        # 清理
        factors = factors.replace([np.inf, -np.inf], np.nan).fillna(0)
        return factors


# ============ 因子评分器 (无 ML 降级路径) ============

class FactorScorer:
    """基于规则的因子打分 — 不需要 LightGBM 的降级路径

    原理: 各因子按预设权重线性加权，生成综合得分 [-100, +100]
    """

    # 因子权重 (正=越大越看涨, 负=越大越看跌)
    FACTOR_WEIGHTS = {
        "mom_5d": 15.0,             # 短期动量
        "mom_10d": 12.0,
        "mom_20d": 10.0,
        "mom_60d": 5.0,             # 长期动量
        "mean_reversion_5d": -10.0,  # 均值回归 (反转)
        "mean_reversion_20d": -8.0,
        "volatility_5d": -5.0,      # 高波动看跌
        "volatility_20d": -3.0,
        "volume_ratio_5d": 8.0,     # 放量看涨
        "volume_ratio_20d": 5.0,
        "obv_slope": 10.0,          # OBV 上升看涨
        "rsi_14": -10.0,            # RSI 高看跌 (反转)
        "macd_hist": 15.0,          # MACD 柱正看涨
        "bb_position": -8.0,        # %B 高看跌 (均值回归)
        "price_range": -3.0,        # 大振幅看跌
        "gap_ratio": 5.0,           # 向上跳空看涨
    }

    @classmethod
    def score(cls, factors: pd.Series) -> float:
        """加权打分 → [-100, +100]"""
        raw_score = 0.0
        for name, weight in cls.FACTOR_WEIGHTS.items():
            val = factors.get(name, 0.0)
            # 截断极端值
            val = float(np.clip(val, -1.0, 1.0))
            raw_score += val * weight

        # 归一化到 [-100, 100]
        max_possible = sum(abs(w) for w in cls.FACTOR_WEIGHTS.values())
        normalized = (raw_score / max_possible) * 100 if max_possible > 0 else 0
        return float(np.clip(normalized, -100, 100))


# ============ LightGBM 模型 (ML 路径) ============

class FactorMLModel:
    """LightGBM 因子模型 — 参考 Qlib LGBModel

    训练目标: 预测未来 5 日收益率方向
    输入: 16 个 Alpha 因子
    输出: 预测得分 [-1, +1]
    """

    def __init__(self, symbol: str, n_future_days: int = 5):
        self.symbol = symbol.upper()
        self.n_future_days = n_future_days
        self.model = None
        self.feature_names: list[str] = []

    @property
    def model_path(self) -> Path:
        return MODEL_DIR / f"lgb_{self.symbol}.txt"

    @property
    def meta_path(self) -> Path:
        return MODEL_DIR / f"lgb_{self.symbol}_meta.json"

    def train(self, df: pd.DataFrame) -> bool:
        """训练 LightGBM 模型"""
        if not HAS_LGB:
            return False

        try:
            # 计算因子
            factors = AlphaFactors.compute_all(df)

            # 标签: 未来 n 日收益率方向
            future_ret = df["close"].shift(-self.n_future_days) / df["close"] - 1
            labels = (future_ret > 0).astype(int)

            # 对齐并去除 NaN
            valid = factors.join(labels.rename("label")).dropna()
            if len(valid) < 50:
                logger.warning(f"[Factor ML] {self.symbol} 训练样本不足 ({len(valid)})")
                return False

            X = valid[factors.columns]
            y = valid["label"]

            # 训练/验证分割 (时间序列: 前 80%)
            split = int(len(X) * 0.8)
            X_train, X_val = X.iloc[:split], X.iloc[split:]
            y_train, y_val = y.iloc[:split], y.iloc[split:]

            train_data = lgb.Dataset(X_train, label=y_train)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

            params = {
                "objective": "binary",
                "metric": "auc",
                "boosting_type": "gbdt",
                "num_leaves": 31,
                "learning_rate": 0.05,
                "feature_fraction": 0.8,
                "bagging_fraction": 0.8,
                "bagging_freq": 5,
                "verbose": -1,
                "seed": 42,
            }

            callbacks = [lgb.log_evaluation(period=0)]  # 静默训练
            self.model = lgb.train(
                params, train_data,
                num_boost_round=200,
                valid_sets=[val_data],
                callbacks=callbacks + [lgb.early_stopping(stopping_rounds=20)],
            )

            self.feature_names = list(X.columns)

            # 保存
            self.model.save_model(str(self.model_path))
            with open(self.meta_path, "w") as f:
                json.dump({
                    "symbol": self.symbol,
                    "features": self.feature_names,
                    "n_future_days": self.n_future_days,
                    "train_samples": len(X_train),
                    "val_auc": float(self.model.best_score.get("valid_0", {}).get("auc", 0)),
                    "timestamp": now_et().isoformat(),
                }, f, indent=2)

            val_auc = self.model.best_score.get("valid_0", {}).get("auc", 0)
            logger.info(
                f"[Factor ML] {self.symbol} 训练完成: "
                f"AUC={val_auc:.4f}, samples={len(X_train)}"
            )
            return True

        except Exception as e:
            logger.error(f"[Factor ML] {self.symbol} 训练失败: {scrub_secrets(str(e))}")
            return False

    def load(self) -> bool:
        """加载缓存模型"""
        if not HAS_LGB:
            return False
        try:
            if not self.model_path.exists():
                return False

            # 检查模型年龄
            age_days = (now_et().timestamp() - self.model_path.stat().st_mtime) / 86400
            if age_days > 90:
                logger.info(f"[Factor ML] {self.symbol} 模型已过期 ({age_days:.0f}d)")
                return False

            self.model = lgb.Booster(model_file=str(self.model_path))

            if self.meta_path.exists():
                with open(self.meta_path) as f:
                    meta = json.load(f)
                self.feature_names = meta.get("features", [])

            logger.info(f"[Factor ML] 加载缓存模型: {self.model_path}")
            return True
        except Exception as e:
            logger.warning(f"[Factor ML] 加载失败: {scrub_secrets(str(e))}")
            return False

    def predict(self, factors: pd.DataFrame) -> float:
        """预测得分 → [-1, +1]"""
        if self.model is None:
            return 0.0

        try:
            # 确保因子列对齐
            if self.feature_names:
                missing = set(self.feature_names) - set(factors.columns)
                for col in missing:
                    factors[col] = 0
                factors = factors[self.feature_names]

            last_row = factors.iloc[[-1]]
            prob = self.model.predict(last_row)[0]

            # prob ∈ [0, 1] → score ∈ [-1, +1]
            score = (prob - 0.5) * 2
            return float(np.clip(score, -1, 1))
        except Exception as e:
            logger.error(f"[Factor ML] 预测失败: {scrub_secrets(str(e))}")
            return 0.0


# ============ FactorStrategy (继承 BaseStrategy) ============

class FactorStrategy(BaseStrategy):
    """Alpha 因子 + ML 信号策略

    搬运自: Qlib (Microsoft, 18k⭐) 因子库 + LGBModel
    原理: 16 个经典 Alpha 因子 → LightGBM 二分类 → 交易信号
    降级: 无 LightGBM 时使用规则打分 (FactorScorer)

    因子类别:
      - 动量: 5/10/20/60 日价格动量
      - 均值回归: 价格偏离 MA 程度
      - 波动率: 5/20 日收益率标准差
      - 成交量: 量比 + OBV 斜率
      - 技术面: RSI + MACD + BB%B
      - 价格形态: 振幅 + 跳空
    """

    name = "alpha_factor"
    version = "1.0"
    timeframes = ["1d"]
    min_data_points = 65   # 因子计算需要至少 60 日数据 + 5 日缓冲
    weight = 1.1           # 因子策略权重略高

    def __init__(
        self,
        use_ml: bool = True,
        n_future_days: int = 5,
        retrain_days: int = 90,
    ):
        self.use_ml = use_ml and HAS_LGB
        self.n_future_days = n_future_days
        self.retrain_days = retrain_days
        self._ml_models: dict[str, FactorMLModel] = {}

    @property
    def ml_available(self) -> bool:
        """ML 路径是否可用"""
        return HAS_LGB

    def _get_ml_model(self, symbol: str, df: pd.DataFrame) -> FactorMLModel | None:
        """获取或训练 ML 模型"""
        if not self.use_ml:
            return None

        symbol = symbol.upper()

        if symbol in self._ml_models:
            return self._ml_models[symbol]

        model = FactorMLModel(symbol, self.n_future_days)

        # 尝试加载缓存
        if model.load():
            self._ml_models[symbol] = model
            return model

        # 训练新模型
        if model.train(df):
            self._ml_models[symbol] = model
            return model

        return None

    def _prepare_dataframe(self, data: MarketData) -> pd.DataFrame:
        """MarketData → DataFrame"""
        df = data.to_dataframe()
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                if col == "volume":
                    df["volume"] = 1_000_000
                elif col == "open":
                    df["open"] = df["close"]
                elif col == "high":
                    df["high"] = df["close"] * 1.01
                elif col == "low":
                    df["low"] = df["close"] * 0.99
        return df

    def analyze(self, data: MarketData) -> TradeSignal:
        """分析市场数据，使用 Alpha 因子 + ML 生成交易信号"""
        default = TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD,
            score=0, strategy_name=self.name,
            confidence=0, reason="Factor analysis unavailable",
        )

        if not self.validate_data(data):
            default.reason = f"数据不足: 需要 {self.min_data_points} 根K线"
            return default

        # 准备数据
        df = self._prepare_dataframe(data)
        factors = AlphaFactors.compute_all(df)
        last_factors = factors.iloc[-1]

        # 构建指标字典
        indicators: dict[str, float] = {
            "price": data.last_close,
            "mom_5d": round(float(last_factors.get("mom_5d", 0)), 4),
            "mom_20d": round(float(last_factors.get("mom_20d", 0)), 4),
            "rsi_14": round(float(last_factors.get("rsi_14", 0.5)), 3),
            "vol_ratio_5d": round(float(last_factors.get("volume_ratio_5d", 1)), 2),
        }

        # 路径 1: ML 预测 (LightGBM)
        ml_score = 0.0
        ml_used = False
        if self.use_ml:
            ml_model = self._get_ml_model(data.symbol, df)
            if ml_model is not None:
                ml_score = ml_model.predict(factors)
                ml_used = True
                indicators["ml_score"] = round(ml_score, 3)

        # 路径 2: 规则打分 (始终计算)
        rule_score = FactorScorer.score(last_factors)
        indicators["rule_score"] = round(rule_score, 1)

        # 合成最终得分
        if ml_used:
            # ML 权重 60%, 规则 40%
            final_score = ml_score * 60 + (rule_score / 100) * 40
            confidence = 0.7
            method = "ML+规则"
        else:
            final_score = rule_score
            confidence = 0.5
            method = "纯规则"

        indicators["final_score"] = round(final_score, 1)
        indicators["method"] = method

        # 映射到信号
        if final_score >= 40:
            signal = SignalType.STRONG_BUY
            reason = f"因子策略({method}) 强烈看涨 (score={final_score:+.1f})"
            return TradeSignal(
                symbol=data.symbol, signal=signal, score=min(85, final_score),
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=confidence, reason=reason, indicators=indicators,
                stop_loss_pct=3.0, take_profit_pct=8.0,
            )
        elif final_score >= 15:
            signal = SignalType.BUY
            reason = f"因子策略({method}) 看涨 (score={final_score:+.1f})"
            return TradeSignal(
                symbol=data.symbol, signal=signal, score=final_score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=confidence * 0.85, reason=reason, indicators=indicators,
                stop_loss_pct=2.5, take_profit_pct=6.0,
            )
        elif final_score <= -40:
            signal = SignalType.STRONG_SELL
            reason = f"因子策略({method}) 强烈看跌 (score={final_score:+.1f})"
            return TradeSignal(
                symbol=data.symbol, signal=signal, score=max(-85, final_score),
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=confidence, reason=reason, indicators=indicators,
            )
        elif final_score <= -15:
            signal = SignalType.SELL
            reason = f"因子策略({method}) 看跌 (score={final_score:+.1f})"
            return TradeSignal(
                symbol=data.symbol, signal=signal, score=final_score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=confidence * 0.85, reason=reason, indicators=indicators,
            )
        else:
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.HOLD,
                score=final_score, strategy_name=self.name,
                timeframe=data.timeframe, confidence=0.3,
                reason=f"因子策略({method}) 中性 (score={final_score:+.1f})",
                indicators=indicators,
            )

    def should_exit(self, data: MarketData, entry_price: float,
                    current_pnl_pct: float) -> TradeSignal | None:
        """因子模型判断是否应退出"""
        signal = self.analyze(data)

        # 强烈看跌且亏损 → 建议退出
        if signal.signal in (SignalType.SELL, SignalType.STRONG_SELL) and current_pnl_pct < 0:
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.SELL,
                score=signal.score, strategy_name=self.name,
                confidence=signal.confidence,
                reason=f"因子策略建议退出 (score={signal.score:+.1f}, pnl={current_pnl_pct:+.1f}%)",
            )
        return None

    def get_factor_report(self, data: MarketData) -> dict[str, Any]:
        """生成详细因子报告 — 用于 Telegram 展示"""
        df = self._prepare_dataframe(data)
        factors = AlphaFactors.compute_all(df)
        last = factors.iloc[-1]

        report = {
            "symbol": data.symbol,
            "timestamp": now_et().isoformat(),
            "factors": {},
            "score": FactorScorer.score(last),
        }

        for name in AlphaFactors.compute_all(df).columns:
            val = float(last.get(name, 0))
            report["factors"][name] = round(val, 4)

        return report
