"""
板块集中度与风险敞口 Mixin

从 risk_manager.py 提取的板块/行业相关方法：
- _check_sector_concentration(): 检查板块集中度
- lookup_sectors(): 查询标的所属行业
- get_risk_exposure_summary(): 生成风险敞口摘要
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SectorMixin:
    """板块集中度与风险敞口混入类

    依赖 RiskManager.__init__ 中初始化的属性:
        self.config            — RiskConfig 实例
        self._symbol_sectors   — 标的行业缓存
        self._today_pnl        — 今日盈亏
    依赖 RiskManager 的方法:
        self._refresh_today_pnl() — 刷新今日盈亏
    """

    def _check_sector_concentration(
        self, symbol: str, new_value: float, current_positions: List[Dict]
    ) -> Optional[str]:
        """检查板块集中度，返回警告信息或None"""
        sector = self._symbol_sectors.get(symbol, "unknown")
        if sector == "unknown":
            return None

        # 计算同板块总敞口
        sector_exposure = new_value
        for p in current_positions:
            p_symbol = p.get('symbol', '').upper()
            p_sector = self._symbol_sectors.get(p_symbol, "unknown")
            if p_sector == sector:
                p_value = p.get('quantity', 0) * (
                    p.get('avg_price', 0) or p.get('avg_cost', 0)
                )
                sector_exposure += p_value

        max_sector = self.config.total_capital * self.config.max_sector_exposure_pct
        if sector_exposure > max_sector:
            return (f"板块[{sector}]总敞口${sector_exposure:.2f}超过上限"
                    f"${max_sector:.2f}({self.config.max_sector_exposure_pct*100}%)")
        return None

    def lookup_sectors(self, symbols: List[str]) -> Dict[str, str]:
        """查询标的所属行业，优先用缓存，缓存未命中时用 yfinance 查询

        返回 {symbol: sector} 映射，查询失败的标记为 '未知'。
        结果会写回 _symbol_sectors 缓存，避免重复查询。
        """
        result: Dict[str, str] = {}
        to_fetch: List[str] = []
        for sym in symbols:
            s = sym.upper()
            cached = self._symbol_sectors.get(s)
            if cached:
                result[s] = cached
            else:
                to_fetch.append(s)

        if to_fetch:
            try:
                import yfinance as yf
                for sym in to_fetch:
                    try:
                        ticker = yf.Ticker(sym)
                        info = ticker.info or {}
                        sector = info.get("sector", "未知")
                        if not sector:
                            sector = "未知"
                    except Exception as e:  # noqa: F841
                        sector = "未知"
                    result[sym] = sector
                    self._symbol_sectors[sym] = sector
            except ImportError:
                # yfinance 不可用，全部标记未知
                for sym in to_fetch:
                    result[sym] = "未知"
                    self._symbol_sectors[sym] = "未知"

        return result

    def get_risk_exposure_summary(
        self, positions: List[Dict], cash: float = 0
    ) -> Dict:
        """生成风险敞口摘要数据，供 /portfolio 展示

        返回包含单只最大占比、行业最大占比、总仓位、日亏损额度等信息的字典。
        """
        self._refresh_today_pnl()

        total_market_value = sum(
            abs(p.get("market_value", 0)) for p in positions
        )
        total_value = total_market_value + cash

        # 单只最大占比
        max_single_sym = ""
        max_single_pct = 0.0
        for p in positions:
            mv = abs(p.get("market_value", 0))
            pct = (mv / total_value * 100) if total_value > 0 else 0
            if pct > max_single_pct:
                max_single_pct = pct
                max_single_sym = p.get("symbol", "?")

        # 行业聚合占比
        sector_values: Dict[str, float] = {}
        symbols = [p.get("symbol", "") for p in positions]
        sector_map = self.lookup_sectors(symbols)
        for p in positions:
            sym = p.get("symbol", "").upper()
            sector = sector_map.get(sym, "未知")
            mv = abs(p.get("market_value", 0))
            sector_values[sector] = sector_values.get(sector, 0) + mv

        max_sector_name = ""
        max_sector_pct = 0.0
        for sector, val in sector_values.items():
            pct = (val / total_value * 100) if total_value > 0 else 0
            if pct > max_sector_pct:
                max_sector_pct = pct
                max_sector_name = sector

        # 总仓位占比
        total_position_pct = (
            (total_market_value / total_value * 100) if total_value > 0 else 0
        )

        # 日亏损额度
        remaining_daily = self.config.daily_loss_limit + self._today_pnl

        return {
            "max_single_symbol": max_single_sym,
            "max_single_pct": round(max_single_pct, 1),
            "max_single_threshold": round(self.config.max_position_pct * 100, 0),
            "max_sector_name": max_sector_name,
            "max_sector_pct": round(max_sector_pct, 1),
            "max_sector_threshold": round(
                self.config.max_sector_exposure_pct * 100, 0
            ),
            "total_position_pct": round(total_position_pct, 1),
            "total_position_threshold": round(
                self.config.max_total_exposure_pct * 100, 0
            ),
            "daily_loss_used": round(abs(min(self._today_pnl, 0)), 2),
            "daily_loss_limit": round(self.config.daily_loss_limit, 2),
            "sector_values": sector_values,
            "sector_map": sector_map,
        }
