"""
DRL 强化学习交易策略 — 搬运自 FinRL (AI4Finance, 11k⭐, MIT)

核心搬运组件:
  - StockTradingEnv (gymnasium 环境) — 简化自 finrl/meta/env_stock_trading/
  - PPO Agent — 直接使用 stable-baselines3 (9.4k⭐, MIT)

架构适配:
  - 继承 BaseStrategy，实现 analyze(MarketData) -> TradeSignal
  - 训练好的模型缓存在 packages/clawbot/src/models/
  - 缺依赖时 graceful degradation → 返回 HOLD

v1.0 — 2026-03-24
"""

import logging
import hashlib
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.strategy_engine import BaseStrategy, MarketData, SignalType, TradeSignal
from src.utils import now_et

logger = logging.getLogger(__name__)

# ============ 可选依赖检测 ============

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYM = True
except ImportError:
    HAS_GYM = False

try:
    from stable_baselines3 import PPO, A2C
    from stable_baselines3.common.vec_env import DummyVecEnv
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

# 模型缓存目录
MODEL_DIR = Path(__file__).parent.parent / "models" / "drl"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ============ 搬运自 FinRL: 简化版 StockTradingEnv ============

if HAS_GYM:
    class StockTradingEnv(gym.Env):
        """单股票交易环境 — 简化自 FinRL env_stocktrading_np.py

        观测空间 (state):
          [balance, shares_held, price, ma5, ma10, ma20, rsi, macd,
           vol_ratio, price_change_5d, price_change_10d]

        动作空间:
          连续值 [-1, 1]
            - action > 0.3  → 买入 (比例 = action)
            - action < -0.3 → 卖出 (比例 = |action|)
            - else          → 持有

        奖励:
          组合收益率变化 (portfolio value change %)
        """

        metadata = {"render_modes": ["human"]}

        def __init__(
            self,
            df: pd.DataFrame,
            initial_amount: float = 100_000.0,
            buy_cost_pct: float = 0.001,
            sell_cost_pct: float = 0.001,
            max_shares: int = 100,
        ):
            super().__init__()
            self.df = df.reset_index(drop=True)
            self.initial_amount = initial_amount
            self.buy_cost_pct = buy_cost_pct
            self.sell_cost_pct = sell_cost_pct
            self.max_shares = max_shares

            # 预计算技术指标
            self._precompute_features()

            # Spaces
            self.n_features = 11  # balance, shares, price, ma5/10/20, rsi, macd, vol_ratio, chg5, chg10
            self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(self.n_features,), dtype=np.float32
            )

            # State
            self.day = 0
            self.balance = initial_amount
            self.shares_held = 0
            self.portfolio_value = initial_amount
            self.prev_portfolio_value = initial_amount

        def _precompute_features(self):
            """预计算所有技术指标特征"""
            close = self.df["close"]
            volume = self.df.get("volume", pd.Series(np.ones(len(close))))

            self.df["ma5"] = close.rolling(5, min_periods=1).mean()
            self.df["ma10"] = close.rolling(10, min_periods=1).mean()
            self.df["ma20"] = close.rolling(20, min_periods=1).mean()

            # RSI
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
            loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
            rs = gain / loss.replace(0, 1e-10)
            self.df["rsi"] = (100 - 100 / (1 + rs)).fillna(50)

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            self.df["macd"] = (ema12 - ema26).fillna(0)

            # Volume ratio
            avg_vol = volume.rolling(20, min_periods=1).mean()
            self.df["vol_ratio"] = (volume / avg_vol.replace(0, 1)).fillna(1).clip(0, 10)

            # Price changes
            self.df["chg5"] = close.pct_change(5).fillna(0).clip(-0.5, 0.5)
            self.df["chg10"] = close.pct_change(10).fillna(0).clip(-0.5, 0.5)

        def _get_state(self) -> np.ndarray:
            """构造观测向量"""
            row = self.df.iloc[self.day]
            price = float(row["close"])

            state = np.array([
                self.balance / self.initial_amount,          # 归一化余额
                self.shares_held / max(self.max_shares, 1),  # 归一化持仓
                price / self.df["close"].iloc[0],            # 归一化价格
                float(row["ma5"]) / price if price > 0 else 1,
                float(row["ma10"]) / price if price > 0 else 1,
                float(row["ma20"]) / price if price > 0 else 1,
                float(row["rsi"]) / 100.0,                  # RSI → [0, 1]
                float(row["macd"]) / price if price > 0 else 0,  # 归一化 MACD
                float(row["vol_ratio"]) / 10.0,              # 成交量比 → [0, 1]
                float(row["chg5"]),
                float(row["chg10"]),
            ], dtype=np.float32)

            return state

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.day = 0
            self.balance = self.initial_amount
            self.shares_held = 0
            self.portfolio_value = self.initial_amount
            self.prev_portfolio_value = self.initial_amount
            return self._get_state(), {}

        def step(self, action):
            price = float(self.df.iloc[self.day]["close"])
            act = float(action[0])

            # 执行交易
            if act > 0.3:  # 买入
                buy_ratio = min(act, 1.0)
                affordable = int(self.balance * buy_ratio / (price * (1 + self.buy_cost_pct)))
                affordable = min(affordable, self.max_shares - self.shares_held)
                if affordable > 0:
                    cost = affordable * price * (1 + self.buy_cost_pct)
                    self.balance -= cost
                    self.shares_held += affordable

            elif act < -0.3:  # 卖出
                sell_ratio = min(abs(act), 1.0)
                sell_qty = int(self.shares_held * sell_ratio)
                if sell_qty > 0:
                    proceeds = sell_qty * price * (1 - self.sell_cost_pct)
                    self.balance += proceeds
                    self.shares_held -= sell_qty

            # 下一天
            self.day += 1
            done = self.day >= len(self.df) - 1
            truncated = False

            if done:
                self.day = len(self.df) - 1

            # 计算组合价值
            new_price = float(self.df.iloc[self.day]["close"])
            self.prev_portfolio_value = self.portfolio_value
            self.portfolio_value = self.balance + self.shares_held * new_price

            # 奖励 = 组合价值变化率
            reward = (self.portfolio_value - self.prev_portfolio_value) / self.prev_portfolio_value
            reward = float(np.clip(reward, -0.1, 0.1))  # 截断极端值

            return self._get_state(), reward, done, truncated, {}


# ============ DRL 策略 (继承 BaseStrategy) ============

class DRLStrategy(BaseStrategy):
    """DRL 强化学习交易策略 — 使用 PPO/A2C 训练的神经网络决策

    搬运自: FinRL (AI4Finance, 11k⭐) + stable-baselines3 (9.4k⭐)
    原理: 将交易建模为马尔可夫决策过程 (MDP)，用 PPO 策略梯度训练 Agent
    适配: 继承 BaseStrategy，analyze() 返回 TradeSignal 参与加权投票

    使用:
      1. 首次使用自动训练 (需 gymnasium + stable-baselines3)
      2. 训练后模型缓存到 src/models/drl/
      3. 后续使用加载缓存模型推理
    """

    name = "drl_ppo"
    version = "1.0"
    timeframes = ["1d"]
    min_data_points = 60   # DRL 需要更多数据
    weight = 1.2           # DRL 权重略高 (高信号质量)

    def __init__(
        self,
        algorithm: str = "ppo",
        train_timesteps: int = 50_000,
        retrain_days: int = 90,
        initial_amount: float = 100_000.0,
    ):
        self.algorithm = algorithm.lower()
        self.train_timesteps = train_timesteps
        self.retrain_days = retrain_days
        self.initial_amount = initial_amount
        self._model = None
        self._model_symbol: str = ""

    @property
    def available(self) -> bool:
        """检查 DRL 依赖是否就绪"""
        return HAS_GYM and HAS_SB3

    def _model_path(self, symbol: str) -> Path:
        """模型缓存路径"""
        return MODEL_DIR / f"{self.algorithm}_{symbol.upper()}.zip"

    def _data_hash(self, data: MarketData) -> str:
        """数据指纹 — 用于判断是否需要重训练"""
        raw = f"{data.symbol}_{len(data.closes)}_{data.closes[-1]:.2f}"
        return hashlib.md5(raw.encode()).hexdigest()[:8]

    def _prepare_dataframe(self, data: MarketData) -> pd.DataFrame:
        """MarketData → pandas DataFrame"""
        df = data.to_dataframe()
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                if col == "volume":
                    df["volume"] = 1_000_000  # 默认成交量
                elif col == "open":
                    df["open"] = df["close"]
                elif col == "high":
                    df["high"] = df["close"] * 1.01
                elif col == "low":
                    df["low"] = df["close"] * 0.99
        return df

    def _train_model(self, df: pd.DataFrame, symbol: str) -> bool:
        """训练 DRL 模型并缓存"""
        if not self.available:
            return False

        try:
            # 用前 80% 数据训练
            train_size = int(len(df) * 0.8)
            train_df = df.iloc[:train_size].copy()

            if len(train_df) < 30:
                logger.warning(f"[DRL] {symbol} 训练数据不足 ({len(train_df)} bars)")
                return False

            env = DummyVecEnv([lambda: StockTradingEnv(
                df=train_df,
                initial_amount=self.initial_amount,
            )])

            if self.algorithm == "a2c":
                model = A2C("MlpPolicy", env, verbose=0, seed=42,
                            learning_rate=7e-4, n_steps=5, gamma=0.99)
            else:  # ppo
                model = PPO("MlpPolicy", env, verbose=0, seed=42,
                            learning_rate=3e-4, n_steps=128, batch_size=64,
                            n_epochs=10, gamma=0.99, clip_range=0.2)

            model.learn(total_timesteps=self.train_timesteps)

            # 缓存
            path = self._model_path(symbol)
            model.save(str(path))
            self._model = model
            self._model_symbol = symbol
            logger.info(f"[DRL] {symbol} 模型训练完成，已缓存: {path}")
            return True

        except Exception as e:
            logger.error(f"[DRL] {symbol} 训练失败: {e}")
            return False

    def _load_or_train(self, data: MarketData) -> bool:
        """加载缓存模型或训练新模型"""
        symbol = data.symbol.upper()

        # 已加载且同一股票
        if self._model is not None and self._model_symbol == symbol:
            return True

        # 尝试加载缓存
        path = self._model_path(symbol)
        if path.exists():
            try:
                age_days = (now_et().timestamp() - path.stat().st_mtime) / 86400
                if age_days < self.retrain_days:
                    if self.algorithm == "a2c":
                        self._model = A2C.load(str(path))
                    else:
                        self._model = PPO.load(str(path))
                    self._model_symbol = symbol
                    logger.info(f"[DRL] 加载缓存模型: {path} (age={age_days:.0f}d)")
                    return True
                else:
                    logger.info(f"[DRL] 模型已过期 ({age_days:.0f}d), 重新训练")
            except Exception as e:
                logger.warning(f"[DRL] 加载模型失败: {e}, 重新训练")

        # 训练新模型
        df = self._prepare_dataframe(data)
        return self._train_model(df, symbol)

    def _predict_action(self, data: MarketData) -> Tuple[float, float]:
        """使用训练好的模型预测动作

        Returns:
            (action_value, confidence)
            action_value: -1 ~ +1 (负=卖出, 正=买入)
            confidence: 0 ~ 1
        """
        if self._model is None:
            return 0.0, 0.0

        try:
            df = self._prepare_dataframe(data)
            # 构造最近一天的环境状态
            env = StockTradingEnv(df=df, initial_amount=self.initial_amount)
            obs, _ = env.reset()

            # 模拟到最后一天
            for i in range(len(df) - 2):
                action, _ = self._model.predict(obs, deterministic=True)
                obs, _, done, _, _ = env.step(action)
                if done:
                    break

            # 最后一步的预测
            action, _ = self._model.predict(obs, deterministic=True)
            act_val = float(action[0])

            # 置信度: 动作越极端越确信
            confidence = min(abs(act_val), 1.0)

            return act_val, confidence

        except Exception as e:
            logger.error(f"[DRL] 预测失败: {e}")
            return 0.0, 0.0

    def analyze(self, data: MarketData) -> TradeSignal:
        """分析市场数据，使用 DRL 模型生成交易信号"""
        default = TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD,
            score=0, strategy_name=self.name,
            confidence=0, reason="DRL unavailable",
        )

        if not self.available:
            default.reason = (
                "DRL 依赖未安装。安装: pip install gymnasium stable-baselines3"
            )
            return default

        if not self.validate_data(data):
            default.reason = f"数据不足: 需要 {self.min_data_points} 根K线"
            return default

        # 加载或训练模型
        if not self._load_or_train(data):
            default.reason = "DRL 模型训练/加载失败"
            return default

        # 预测
        action, confidence = self._predict_action(data)

        indicators = {
            "drl_action": round(action, 3),
            "drl_confidence": round(confidence, 3),
            "algorithm": self.algorithm.upper(),
            "price": data.last_close,
        }

        # 映射动作到信号
        if action > 0.3:
            score = min(85, 40 + action * 50)
            signal = SignalType.STRONG_BUY if action > 0.7 else SignalType.BUY
            reason = f"DRL {self.algorithm.upper()} 看涨 (action={action:+.2f})"
            return TradeSignal(
                symbol=data.symbol, signal=signal, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=max(0.5, confidence),
                reason=reason, indicators=indicators,
                stop_loss_pct=3.0, take_profit_pct=8.0,
            )
        elif action < -0.3:
            score = max(-85, -40 + action * 50)
            signal = SignalType.STRONG_SELL if action < -0.7 else SignalType.SELL
            reason = f"DRL {self.algorithm.upper()} 看跌 (action={action:+.2f})"
            return TradeSignal(
                symbol=data.symbol, signal=signal, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=max(0.5, confidence),
                reason=reason, indicators=indicators,
            )
        else:
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.HOLD,
                score=action * 30,  # 微弱方向
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.3,
                reason=f"DRL {self.algorithm.upper()} 中性 (action={action:+.2f})",
                indicators=indicators,
            )

    def should_exit(self, data: MarketData, entry_price: float,
                    current_pnl_pct: float) -> Optional[TradeSignal]:
        """DRL 模型判断是否应退出"""
        if not self.available or self._model is None:
            return None

        action, confidence = self._predict_action(data)

        # DRL 明确看跌 → 建议退出
        if action < -0.5 and confidence > 0.5:
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.SELL,
                score=-60, strategy_name=self.name,
                confidence=confidence,
                reason=f"DRL 建议退出 (action={action:+.2f}, pnl={current_pnl_pct:+.1f}%)",
            )
        return None
