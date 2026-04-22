"""
ClawBot RPC Bridge
搬运自 freqtrade/rpc/rpc.py 模式
统一的业务逻辑聚合层 — API 和 Telegram 共享同一套方法

Design principles:
  1. Every method is @staticmethod — no instance state, easy to call from anywhere
  2. Lazy imports inside each method — avoids circular dependency hell
  3. Every external call wrapped in try/except — one broken subsystem never crashes the API
  4. Sync methods for fast reads, async methods only when calling async subsystems
"""

import os
import time
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


def _safe_error(e: Exception) -> str:
    """脱敏异常信息,隐藏内部路径和技术细节"""
    msg = str(e)
    # 移除文件路径
    import re

    msg = re.sub(r"[/\\][\w/\\.-]+\.py", "[内部模块]", msg)
    msg = re.sub(r"line \d+", "", msg)
    # 截断过长信息
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return msg


# Track process startup time for uptime calculation
_start_time = time.time()


class ClawBotRPC:
    """
    Central RPC class — bridges internal state to external consumers.

    Pattern: freqtrade's RPC abstraction where one class serves both
    REST API and Telegram handler.  All business logic lives here;
    transport layers (FastAPI routes, Telegram handlers) are thin wrappers.
    """

    # ──────────────────────────────────────────────
    #  System
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_ping() -> dict:
        """Health-check ping — always succeeds."""
        return {"status": "pong", "version": "5.0"}

    @staticmethod
    def _rpc_system_status() -> dict:
        """Aggregate full system status for dashboard display."""
        from src.bot.globals import (
            bot_registry,
            shared_memory,
        )
        from src.broker_selector import ibkr
        from src.litellm_router import free_pool

        uptime = time.time() - _start_time

        # ── Bot statuses ──
        bot_statuses = []
        for bot_id, bot in bot_registry.items():
            try:
                alive = bool(bot.app and bot.app.updater and bot.app.updater.running)
            except Exception as e:  # noqa: F841
                alive = False
            bot_statuses.append(
                {
                    "bot_id": bot_id,
                    "username": getattr(bot, "username", ""),
                    "model": getattr(bot, "model", ""),
                    "alive": alive,
                    "api_type": getattr(bot, "api_type", ""),
                    "message_count": getattr(bot, "_message_count", 0),
                    "error_count": getattr(bot, "_error_count", 0),
                }
            )

        # ── Free API pool stats ──
        pool_stats: dict = {}
        try:
            pool_stats = free_pool.get_stats()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # ── IBKR broker status ──
        ibkr_connected = False
        ibkr_account = ""
        try:
            # 优先通过 IBKRBridge 实例检测（运行时有效）
            ibkr_connected = getattr(ibkr, "_connected", False) if ibkr else False
            ibkr_account = getattr(ibkr, "account", "") or ""
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        # 兜底：如果 IBKRBridge 实例不可用，直接检测 4002 端口
        if not ibkr_connected:
            try:
                import socket as _socket

                _ibkr_port = int(os.environ.get("IBKR_PORT", "4002"))
                with _socket.create_connection(("127.0.0.1", _ibkr_port), timeout=1):
                    ibkr_connected = True
            except Exception as e:
                logger.debug("[RPC] IBKR连接检测失败: %s", e)

        # ── Shared memory stats ──
        mem_entries = 0
        try:
            mem_stats = shared_memory.get_stats()
            mem_entries = mem_stats.get("total_entries", 0)
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # ── 闲鱼客服状态检测 ──
        xianyu_online = False
        xianyu_detail: dict = {"online": False, "service": "xianyu_live"}
        try:
            import subprocess

            result = subprocess.run(["pgrep", "-f", "xianyu_main"], capture_output=True, text=True, timeout=3)
            xianyu_online = result.returncode == 0 and bool(result.stdout.strip())
            xianyu_detail["online"] = xianyu_online

            # 如果闲鱼进程在线，通过内部 admin API 拉取详细状态
            if xianyu_online:
                try:
                    import httpx
                    _xy_headers = {"X-API-Token": os.environ.get("OPENCLAW_API_TOKEN", "")}
                    # 拉取 WS 连接 + Cookie 状态
                    _xy_r = httpx.get("http://127.0.0.1:18800/api/status", timeout=3, headers=_xy_headers)
                    if _xy_r.status_code == 200:
                        _xs = _xy_r.json()
                        xianyu_detail["cookie_ok"] = _xs.get("cookie_ok", False)
                        xianyu_detail["auto_reply_active"] = _xs.get("ws_connected", False) and _xs.get("cookie_ok", False)
                    # 拉取今日咨询数
                    _xy_r2 = httpx.get("http://127.0.0.1:18800/api/dashboard", timeout=3, headers=_xy_headers)
                    if _xy_r2.status_code == 200:
                        _xy_dash = _xy_r2.json()
                        _xy_today = _xy_dash.get("today", {})
                        xianyu_detail["conversations_today"] = _xy_today.get("consultations", 0)
                        xianyu_detail["unread_chats"] = _xy_today.get("consultations", 0)
                except Exception:
                    # 闲鱼 admin 不可用时静默降级
                    logger.debug("闲鱼 admin API 不可用，使用基础状态")
        except Exception as e:
            logger.debug("闲鱼状态检测失败: %s", e)

        # ── 微信领券功能状态检测 ──
        wechat_connected = False
        try:
            import json

            token_file = os.path.expanduser("~/.openclaw/coupon_token.json")
            if os.path.exists(token_file):
                with open(token_file, encoding="utf-8") as f:
                    data = json.load(f)
                # 修复：字段名是 "token" 而不是 "session_token"
                wechat_connected = bool(data.get("token"))
        except Exception as e:
            logger.debug("微信状态检测失败: %s", e)

        return {
            "uptime_seconds": uptime,
            "bots": bot_statuses,
            "ibkr_connected": ibkr_connected,
            "ibkr_account": ibkr_account,
            "pool_active_sources": pool_stats.get("active_sources", 0),
            "pool_total_sources": pool_stats.get("total_sources", 0),
            "pool_routing_strategy": pool_stats.get("routing_strategy", "balanced"),
            "total_api_calls": pool_stats.get("total_requests", 0),
            "total_cost_usd": pool_stats.get("total_cost_usd", 0.0),
            "avg_latency_ms": pool_stats.get("avg_latency_ms", 0.0),
            "memory_entries": mem_entries,
            "xianyu": xianyu_detail,
            "wechat": {"connected": wechat_connected, "service": "coupon_auto"},
        }

    # ──────────────────────────────────────────────
    #  Trading — Positions
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trading_positions() -> dict:
        """Get current positions from IBKR or local portfolio fallback.

        Returns dict with keys: connected, positions (list), account_summary.
        IBKR bridge methods (get_positions, get_account_summary) are async.
        """
        from src.broker_selector import ibkr
        from src.invest_tools import portfolio

        connected = False
        positions: List[dict] = []
        account_summary: dict = {}

        try:
            connected = ibkr.connected if ibkr else False
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        if connected:
            # ── Live IBKR positions ──
            try:
                raw_positions = await ibkr.get_positions()
                for p in raw_positions or []:
                    qty = float(p.get("quantity", 0) or 0)
                    positions.append(
                        {
                            "symbol": p.get("symbol", ""),
                            "quantity": qty,
                            "avg_price": float(p.get("avg_price", 0) or p.get("avg_cost", 0) or 0),
                            "current_price": float(p.get("market_price", 0) or 0),
                            "unrealized_pnl": float(p.get("unrealized_pnl", 0) or 0),
                            "unrealized_pnl_pct": float(p.get("unrealized_pnl_pct", 0) or 0),
                            "market_value": float(p.get("market_value", 0) or 0),
                            "side": "short" if qty < 0 else "long",
                        }
                    )
                # 兜底：如果 IBKR 没返回实时价格，用 yfinance 补齐
                symbols_needing_price = [p["symbol"] for p in positions if not p.get("current_price")]
                if symbols_needing_price:
                    try:
                        import yfinance as yf
                        tickers = yf.Tickers(" ".join(symbols_needing_price))
                        for sym in symbols_needing_price:
                            try:
                                info = tickers.tickers[sym].fast_info
                                price = float(getattr(info, "last_price", 0) or 0)
                                if not price:
                                    price = float(getattr(info, "previous_close", 0) or 0)
                                for p in positions:
                                    if p["symbol"] == sym and price > 0:
                                        p["current_price"] = price
                                        p["market_value"] = p["quantity"] * price
                                        cost = p["quantity"] * p["avg_price"]
                                        p["unrealized_pnl"] = p["market_value"] - cost
                            except Exception:
                                pass
                    except ImportError:
                        logger.debug("yfinance 未安装，跳过价格补齐")
            except Exception as e:
                logger.warning("Failed to get IBKR positions: %s", e)

            try:
                account_summary = await ibkr.get_account_summary() or {}
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
        else:
            # ── Fallback: local Portfolio (sync) + yfinance live prices ──
            try:
                local_positions = portfolio.get_positions() if portfolio else []
                symbols = [p.get("symbol", "") for p in local_positions or [] if p.get("symbol")]

                # Batch-fetch current prices via yfinance (already a project dependency)
                live_prices: dict = {}
                if symbols:
                    try:
                        import yfinance as yf
                        tickers = yf.Tickers(" ".join(symbols))
                        for sym in symbols:
                            try:
                                info = tickers.tickers[sym].fast_info
                                price = float(getattr(info, "last_price", 0) or 0)
                                if price <= 0:
                                    price = float(getattr(info, "previous_close", 0) or 0)
                                live_prices[sym] = price
                            except Exception:
                                live_prices[sym] = 0.0
                    except Exception as e_yf:
                        logger.warning("yfinance price fetch failed (degraded to zeros): %s", e_yf)

                for p in local_positions or []:
                    qty = float(p.get("quantity", 0) or 0)
                    avg_price = float(p.get("avg_price", 0) or p.get("avg_cost", 0) or 0)
                    sym = p.get("symbol", "")
                    current_price = live_prices.get(sym, 0.0)
                    market_value = qty * current_price if qty and current_price else 0.0
                    cost_basis = qty * avg_price if qty and avg_price else 0.0
                    unrealized_pnl = market_value - cost_basis
                    unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0
                    positions.append(
                        {
                            "symbol": sym,
                            "quantity": qty,
                            "avg_price": avg_price,
                            "current_price": round(current_price, 2),
                            "unrealized_pnl": round(unrealized_pnl, 2),
                            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                            "market_value": round(market_value, 2),
                            "side": "short" if qty < 0 else "long",
                        }
                    )
            except Exception as e:
                logger.warning("Failed to get local positions: %s", e)

        return {
            "connected": connected,
            "positions": positions,
            "account_summary": (account_summary if isinstance(account_summary, dict) else {}),
        }

    # ──────────────────────────────────────────────
    #  Trading — PnL
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trading_pnl() -> dict:
        """Get PnL summary from trading journal + IBKR account."""
        from src.broker_selector import ibkr
        from src.trading_journal import journal

        result = {
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "daily_pnl": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0,
            "account_value": 0.0,
            "cash": 0.0,
            "buying_power": 0.0,
        }

        # ── From local trading journal ──
        try:
            if journal:
                stats = journal.get_stats() if hasattr(journal, "get_stats") else {}
                result["total_trades"] = stats.get("total_trades", 0)
                result["winning_trades"] = stats.get("winning_trades", 0)
                result["losing_trades"] = stats.get("losing_trades", 0)
                result["win_rate"] = stats.get("win_rate", 0.0)
                result["total_pnl"] = stats.get("total_pnl", 0.0)
                result["sharpe_ratio"] = stats.get("sharpe_ratio", 0.0)
                result["max_drawdown"] = stats.get("max_drawdown", 0.0)
        except Exception as e:
            logger.warning("Failed to get journal stats: %s", e)

        # ── From IBKR account summary (async) ──
        try:
            if ibkr and ibkr.connected:
                summary = await ibkr.get_account_summary() or {}
                result["account_value"] = float(summary.get("NetLiquidation", 0) or 0)
                result["cash"] = float(summary.get("TotalCashValue", 0) or 0)
                result["buying_power"] = float(summary.get("BuyingPower", 0) or 0)
                result["daily_pnl"] = float(summary.get("RealizedPnL", 0) or summary.get("DailyPnL", 0) or 0)
        except Exception as e:
            logger.warning("Failed to get IBKR account summary: %s", e)

        return result

    # ──────────────────────────────────────────────
    #  Trading — Dashboard (图表+资产)
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trading_dashboard() -> dict:
        """盈利仪表盘数据：图表+资产+连接状态"""
        from src.broker_selector import ibkr
        from src.trading_journal import journal

        try:
            # 获取最近 30 天的每日净值数据
            chart_data: list = []
            assets: list = []
            connected = False

            # 检查 IBKR 连接状态
            try:
                connected = ibkr.connected if ibkr else False
            except Exception as e:
                logger.debug("[RPC] IBKR 连接状态检查失败: %s", e)

            # 尝试获取持仓作为资产列表
            try:
                if connected and ibkr:
                    positions = await ibkr.get_positions()
                    for pos in positions or []:
                        assets.append(
                            {
                                "name": pos.get("symbol", "Unknown"),
                                "value": float(pos.get("market_value", 0)),
                                "pnl": float(pos.get("unrealized_pnl", 0)),
                            }
                        )
            except Exception as e:
                logger.debug("[RPC] IBKR 持仓查询失败: %s", e)

            # 用真实交易日志生成净值曲线，避免前端长期看到空图
            try:
                equity_values, date_labels = journal.get_equity_curve(days=30)
                chart_data = [{"name": label, "value": value} for label, value in zip(date_labels, equity_values)]
            except Exception as e:
                logger.debug("[RPC] 交易净值曲线生成失败: %s", e)

            return {"chart_data": chart_data, "assets": assets, "connected": connected}
        except Exception as e:
            logger.debug("[RPC] 交易面板数据获取失败: %s", e)
            return {"chart_data": [], "assets": [], "connected": False}

    # ──────────────────────────────────────────────
    #  Trading — Strategy Signals
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_trading_signals() -> list:
        """Get recent strategy engine signal history."""
        import src.bot.globals as g

        signals: list = []
        engine = g.strategy_engine_instance
        if not engine:
            return signals

        try:
            history = engine.get_history(limit=20)
            for entry in history or []:
                signals.append(
                    {
                        "symbol": entry.get("symbol", ""),
                        "signal": entry.get("signal", "HOLD"),
                        "score": entry.get("score", 0),
                        "confidence": entry.get("confidence", 0.0),
                        "strategy_name": entry.get("strategy_name", ""),
                        "reason": entry.get("reason", ""),
                        "timestamp": entry.get("ts", ""),
                    }
                )
        except Exception as e:
            logger.warning("Failed to get strategy signals: %s", e)

        return signals

    # ──────────────────────────────────────────────
    #  Trading — System Status
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_trading_system_status() -> dict:
        """Get auto-trading system status (risk manager, pipeline, etc.)."""
        from src.trading_system import get_system_status

        try:
            return get_system_status() or {}
        except Exception as e:
            logger.warning("Failed to get trading system status: %s", e)
            return {}

    # ──────────────────────────────────────────────
    #  Trading — AI Team Vote
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trigger_team_vote(
        symbol: str,
        analysis: dict,
        *,
        timeout_per_bot: float = 60,
        account_context: str = "",
    ) -> dict:
        """Trigger AI team vote for a symbol.

        ``analysis`` must be the pre-computed technical-analysis dict
        (from ``get_full_analysis``).  The caller is responsible for
        preparing it before invoking this RPC.

        Args:
            symbol: Ticker / symbol code.
            analysis: Technical analysis data dict.
            timeout_per_bot: Per-bot timeout in seconds.
            account_context: Optional account context string.

        Returns:
            VoteResult dict on success, or ``{"error": "..."}`` on failure.
        """
        from src.trading_system import _ai_team_api_callers
        from src.ai_team_voter import run_team_vote

        if not _ai_team_api_callers:
            return {"error": "AI team callers not initialized"}

        try:
            result = await run_team_vote(
                symbol=symbol,
                analysis=analysis,
                api_callers=_ai_team_api_callers,
                timeout_per_bot=timeout_per_bot,
                account_context=account_context,
            )
            # VoteResult is a dataclass — convert to dict if needed
            if hasattr(result, "__dict__") and not isinstance(result, dict):
                return vars(result)
            return result or {}
        except Exception as e:
            logger.error("Team vote failed for %s: %s", symbol, e)
            return {"error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  Social
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_social_status() -> dict:
        """Get social-media autopilot status via browser worker.

        Calls the social_browser_worker "status" action to retrieve real
        browser/cookie connection status for each platform.  Falls back
        to cookie-file detection, then placeholder data if the worker
        is unavailable.

        使用线程超时保护（2秒），防止 worker 子进程启动慢导致前端超时。
        """
        # 辅助函数: 检查 Cookie 文件是否存在且有效
        def _check_cookie_file(platform: str) -> bool:
            """检查 ~/.openclaw/ 下对应平台的 Cookie 文件"""
            from pathlib import Path
            import json as _json
            cookie_files = {
                "x": Path.home() / ".openclaw" / "x_cookies.json",
                "xhs": Path.home() / ".openclaw" / "xhs_cookies.json",
            }
            path = cookie_files.get(platform)
            if not path or not path.exists():
                return False
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
                # X 的 Cookie 文件由 twikit 直接管理（非空即可）
                if platform == "x":
                    return bool(data)
                # XHS 的 Cookie 文件：支持 {cookie: "..."} 和 {a1: "...", web_session: "..."} 两种格式
                if platform == "xhs":
                    return bool(data.get("cookie", "")) or (isinstance(data, dict) and bool(data.get("a1", "")))
                return False
            except Exception:
                return False

        _placeholder = {
            "autopilot_running": False,
            "running": False,
            "platforms": [
                {
                    "platform": "x",
                    "connected": _check_cookie_file("x"),
                    "last_post_time": "",
                    "posts_today": 0,
                    "total_posts": 0,
                },
                {
                    "platform": "xhs",
                    "connected": _check_cookie_file("xhs"),
                    "last_post_time": "",
                    "posts_today": 0,
                    "total_posts": 0,
                },
            ],
            "next_scheduled_action": "",
            "next_scheduled_time": "",
            "content_queue_size": 0,
            "source": "placeholder",
        }

        # 使用线程超时保护：最多等 2 秒，超时直接返回 placeholder
        import concurrent.futures

        def _fetch_worker_status():
            """在子线程中调用 worker，防止阻塞主线程过久"""
            from src.execution.social.worker_bridge import run_social_worker
            return run_social_worker("status", {})

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_fetch_worker_status)
                try:
                    result = future.result(timeout=2.0)
                except concurrent.futures.TimeoutError:
                    logger.warning("Social status worker 超时(2s)，返回 Cookie 文件状态兜底")
                    _placeholder["source"] = "timeout_fallback"
                    return _placeholder
            if not result.get("success"):
                logger.warning("Social status worker failed: %s", result.get("error"))
                # Worker 不可用时，用 Cookie 文件状态兜底
                return _placeholder

            # Map worker response to API schema
            x_status = result.get("x", {})
            xhs_status = result.get("xhs", {})

            # Worker 返回的 connected 和 Cookie 文件检测 取 OR（任一为真即认为已连接）
            x_connected = x_status.get("connected", False) or _check_cookie_file("x")
            xhs_connected = xhs_status.get("connected", False) or _check_cookie_file("xhs")

            # 同时提供 running 字段，兼容前端读取 r.running ?? r.active
            _autopilot_running = result.get("autopilot_running", False)
            return {
                "autopilot_running": _autopilot_running,
                "running": _autopilot_running,
                "platforms": [
                    {
                        "platform": "x",
                        "connected": x_connected,
                        "last_post_time": x_status.get("last_post_time", ""),
                        "posts_today": x_status.get("posts_today", 0),
                        "total_posts": x_status.get("total_posts", 0),
                    },
                    {
                        "platform": "xhs",
                        "connected": xhs_connected,
                        "last_post_time": xhs_status.get("last_post_time", ""),
                        "posts_today": xhs_status.get("posts_today", 0),
                        "total_posts": xhs_status.get("total_posts", 0),
                    },
                ],
                "next_scheduled_action": result.get("next_scheduled_action", ""),
                "next_scheduled_time": result.get("next_scheduled_time", ""),
                "content_queue_size": result.get("content_queue_size", 0),
            }
        except Exception as e:
            logger.warning("Social status check failed, using cookie-file fallback: %s", e)
            return _placeholder

    @staticmethod
    def _rpc_social_browser_status() -> dict:
        """Get browser session readiness for X / 小红书.

        综合检查: browser worker 状态 + Cookie 文件状态。
        任一路径可用即视为 ready。
        """
        try:
            from src.execution import execution_hub
            from pathlib import Path
            import json as _json

            status = execution_hub.get_social_browser_status() or {}
            x_ready = status.get("x_ready")
            xhs_ready = status.get("xiaohongshu_ready")

            # 额外检查 Cookie 文件（twikit / xhs 持久化登录）
            x_cookie_ok = False
            xhs_cookie_ok = False
            try:
                x_path = Path.home() / ".openclaw" / "x_cookies.json"
                if x_path.exists():
                    data = _json.loads(x_path.read_text(encoding="utf-8"))
                    x_cookie_ok = bool(data)
            except Exception as e:
                logger.debug("读取X Cookie文件异常: %s", e)
            try:
                xhs_path = Path.home() / ".openclaw" / "xhs_cookies.json"
                if xhs_path.exists():
                    data = _json.loads(xhs_path.read_text(encoding="utf-8"))
                    xhs_cookie_ok = bool(data.get("cookie", "")) or (isinstance(data, dict) and bool(data.get("a1", "")))
            except Exception as e:
                logger.debug("读取XHS Cookie文件异常: %s", e)

            def _map_ready(value, cookie_ok: bool):
                if value is True or cookie_ok:
                    return "ready"
                if value is False:
                    return "login_needed"
                return "unknown"

            return {
                "browser_running": bool(status.get("browser_running", False)),
                "x": _map_ready(x_ready, x_cookie_ok),
                "xhs": _map_ready(xhs_ready, xhs_cookie_ok),
            }
        except Exception as e:
            logger.warning("Social browser status failed: %s", e)
            # 即使主逻辑失败，也检查 Cookie 文件
            x_cookie = "unknown"
            xhs_cookie = "unknown"
            try:
                from pathlib import Path
                import json as _json
                x_path = Path.home() / ".openclaw" / "x_cookies.json"
                if x_path.exists() and bool(_json.loads(x_path.read_text(encoding="utf-8"))):
                    x_cookie = "ready"
                xhs_path = Path.home() / ".openclaw" / "xhs_cookies.json"
                if xhs_path.exists() and bool(_json.loads(xhs_path.read_text(encoding="utf-8")).get("cookie", "")):
                    xhs_cookie = "ready"
            except Exception as e:
                logger.debug("降级读取Cookie文件异常: %s", e)
            return {
                "browser_running": False,
                "x": x_cookie,
                "xhs": xhs_cookie,
                "error": _safe_error(e),
            }

    @staticmethod
    def _rpc_social_analytics(days: int = 7) -> dict:
        """Get analytics data used by the desktop social dashboard."""
        try:
            from src.execution import execution_hub

            report = execution_hub.get_post_performance_report(days=days) or {}
            by_platform = report.get("by_platform", {}) or {}
            top_posts = report.get("top_posts", []) or []

            engagement = {
                platform: {
                    "total_likes": int(stats.get("likes", 0) or 0),
                    "total_comments": int(stats.get("comments", 0) or 0),
                    "total_shares": int(stats.get("shares", 0) or 0),
                }
                for platform, stats in by_platform.items()
            }
            follower_growth = {
                platform: {
                    "current": int(stats.get("posts", 0) or 0),
                    "net_change": 0,
                }
                for platform, stats in by_platform.items()
            }

            normalized_top_posts = [
                {
                    "preview": post.get("topic") or post.get("url") or "无标题",
                    "title": post.get("topic") or "",
                    "likes": int(post.get("likes", 0) or 0),
                    "comments": int(post.get("comments", 0) or 0),
                    "shares": int(post.get("shares", 0) or 0),
                }
                for post in top_posts
            ]

            return {
                "days": days,
                "engagement": engagement,
                "follower_growth": follower_growth,
                "top_posts": normalized_top_posts,
                "success": bool(report.get("success", True)),
            }
        except Exception as e:
            logger.warning("Social analytics failed: %s", e)
            return {
                "days": days,
                "engagement": {},
                "follower_growth": {},
                "top_posts": [],
                "success": False,
                "error": _safe_error(e),
            }

    @staticmethod
    async def _rpc_social_discover_topics(count: int = 5) -> dict:
        """Discover hot topics for content creation."""
        try:
            from src.execution.social.content_strategy import discover_hot_topics

            topics = await discover_hot_topics(count=count)
            return {"topics": topics or [], "status": "ok"}
        except Exception as e:
            logger.error("Topic discovery failed: %s", e)
            return {"topics": [], "status": "error", "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_compose(
        topic: str,
        platform: str = "x",
        persona_name: str = "default",
    ) -> dict:
        """AI content generation pipeline (搬运 content_strategy.py 的 compose 链).

        Full pipeline: load persona -> derive strategy -> compose post.
        Returns generated text ready for user review or direct publish.
        """
        try:
            from src.execution.social.content_strategy import (
                compose_post,
                derive_content_strategy,
                load_persona,
            )

            # Load persona
            persona = load_persona(name=persona_name)

            # Derive strategy
            strategy_result = await derive_content_strategy(
                topic=topic,
                platform=platform,
                persona=persona,
            )
            strategy = strategy_result.get("strategy") if strategy_result.get("success") else None

            # Compose post
            max_len = 280 if platform == "x" else 800
            result = await compose_post(
                topic=topic,
                platform=platform,
                strategy=strategy,
                persona=persona,
                max_length=max_len,
            )

            if result.get("success"):
                return {
                    "success": True,
                    "text": result["text"],
                    "platform": platform,
                    "strategy": strategy,
                    "char_count": len(result["text"]),
                }
            return {"success": False, "error": result.get("error", "Content generation failed")}

        except Exception as e:
            logger.error("Social compose failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_publish(
        platform: str,
        content: str,
    ) -> dict:
        """Publish content to a social platform via adapter pattern.

        通过适配器注册表统一分发，支持 "both" 同时发布到所有平台。
        """
        from src.execution.social.platform_adapter import get_adapter, get_all_adapters
        from src.execution.social.worker_bridge import run_social_worker_async

        try:
            if platform == "both":
                # 同时发布到所有已注册平台
                results = {}
                any_success = False
                for pid, adapter in get_all_adapters().items():
                    try:
                        title, body = adapter.normalize_content(content)
                        payload = adapter.build_worker_payload(body, title)
                        result = await run_social_worker_async(adapter.worker_action, payload)
                        results[pid] = result
                        if result.get("success"):
                            any_success = True
                    except Exception as e:
                        logger.warning("发布到 %s 失败: %s", adapter.display_name, e)
                        results[pid] = {"success": False, "error": str(e)}
                results["success"] = any_success
                return results

            # 单平台发布
            adapter = get_adapter(platform)
            if adapter:
                title, body = adapter.normalize_content(content)
                payload = adapter.build_worker_payload(body, title)
                return await run_social_worker_async(adapter.worker_action, payload)
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
        except Exception as e:
            logger.error("Social publish failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_research(topic: str, count: int = 10) -> dict:
        """Deep topic research via browser worker.

        Delegates to the social_browser_worker "research" action which
        scrapes platform data and aggregates insights for the given topic.
        """
        from src.execution.social.worker_bridge import run_social_worker_async

        try:
            result = await run_social_worker_async("research", {"topic": topic, "count": count})
            return result
        except Exception as e:
            logger.error("Social research failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_metrics() -> dict:
        """Get social metrics/analytics via browser worker.

        Returns follower counts, engagement stats, and growth data
        from the social_browser_worker "metrics" action.
        同时注入 running 字段，兼容前端读取 r.running ?? r.active。
        """
        from src.execution.social.worker_bridge import run_social_worker_async

        try:
            result = await run_social_worker_async("metrics", {})
            # 兼容前端：如果 worker 返回了 autopilot_running，同步到 running 字段
            if isinstance(result, dict) and "autopilot_running" in result:
                result.setdefault("running", result["autopilot_running"])
            return result
        except Exception as e:
            logger.error("Social metrics failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  Social — Drafts
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_social_drafts() -> dict:
        """List all drafts from autopilot state."""
        from src.social_scheduler import _load_state

        state = _load_state()
        return {"drafts": state.get("drafts", []), "count": len(state.get("drafts", []))}

    @staticmethod
    def _rpc_social_draft_update(index: int, text: str) -> dict:
        """Update a draft's text content."""
        from src.social_scheduler import _load_state, _save_state

        state = _load_state()
        drafts = state.get("drafts", [])
        if 0 <= index < len(drafts):
            drafts[index]["text"] = text
            drafts[index]["status"] = "edited"
            state["drafts"] = drafts
            _save_state(state)
            return {"success": True}
        return {"success": False, "error": "Invalid draft index"}

    @staticmethod
    def _rpc_social_draft_delete(index: int) -> dict:
        """Delete a draft by index."""
        from src.social_scheduler import _load_state, _save_state

        state = _load_state()
        drafts = state.get("drafts", [])
        if 0 <= index < len(drafts):
            drafts.pop(index)
            state["drafts"] = drafts
            _save_state(state)
            return {"success": True}
        return {"success": False, "error": "Invalid draft index"}

    @staticmethod
    async def _rpc_social_draft_publish(index: int) -> dict:
        """Publish a draft immediately."""
        from src.social_scheduler import _load_state, _save_state
        from src.execution.social.worker_bridge import run_social_worker
        import asyncio

        state = _load_state()
        drafts = state.get("drafts", [])
        if not (0 <= index < len(drafts)):
            return {"success": False, "error": "Invalid draft index"}

        draft = drafts[index]
        platform = draft.get("platform", "x")
        content = draft.get("text", "")

        if platform in ("x", "twitter"):
            result = await asyncio.to_thread(run_social_worker, "publish_x", {"text": content})
        elif platform in ("xhs", "xiaohongshu"):
            title = content.split("\n")[0][:50] if "\n" in content else content[:50]
            body = content[len(title) :].strip() if "\n" in content else content
            result = await asyncio.to_thread(run_social_worker, "publish_xhs", {"title": title, "body": body})
        else:
            result = {"success": False, "error": f"Unknown platform: {platform}"}

        if result.get("success"):
            drafts[index]["status"] = "published"
            state["drafts"] = drafts
            _save_state(state)

        return result

    # ──────────────────────────────────────────────
    #  Social — Autopilot
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_autopilot_status() -> dict:
        """Get social autopilot scheduler status."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().status()
        except Exception as e:
            logger.warning("Autopilot status failed: %s", e)
            return {"running": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_autopilot_start() -> dict:
        """Start the social autopilot scheduler."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().start()
        except Exception as e:
            logger.error("Autopilot start failed: %s", e)
            return {"status": "error", "error": _safe_error(e)}

    @staticmethod
    def _rpc_autopilot_stop() -> dict:
        """Stop the social autopilot scheduler."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().stop()
        except Exception as e:
            logger.error("Autopilot stop failed: %s", e)
            return {"status": "error", "error": _safe_error(e)}

    @staticmethod
    def _rpc_autopilot_trigger(job_id: str) -> dict:
        """Manually trigger a specific autopilot job."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().trigger_job(job_id)
        except Exception as e:
            logger.error("Autopilot trigger failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_social_personas() -> list:
        """List available social personas from data/social_personas/.

        Reads JSON files from the personas directory and returns a summary
        list with id, name, active status, and platform_style for each.
        """
        import json
        from pathlib import Path

        personas: list = []
        persona_dir = Path(__file__).resolve().parent.parent.parent / "data" / "social_personas"
        if not persona_dir.is_dir():
            return personas

        try:
            for f in sorted(persona_dir.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    personas.append(
                        {
                            "id": f.stem,
                            "name": data.get("name", f.stem),
                            "active": data.get("active", True),
                            "platform_style": data.get("platform_style", {}),
                        }
                    )
                except Exception as e:  # noqa: F841
                    continue
        except Exception as e:
            logger.warning("Failed to list personas: %s", e)

        return personas

    @staticmethod
    async def _rpc_social_calendar(days: int = 7) -> dict:
        """Generate a content calendar for the next N days.

        Uses discover_hot_topics to gather trending topics and formats
        them into a simple day-by-day content plan.
        """
        try:
            from src.execution.social.content_strategy import discover_hot_topics

            topics = await discover_hot_topics(count=days * 2)
            calendar: list = []
            for i in range(days):
                day_topics = topics[i * 2 : i * 2 + 2] if topics else []
                calendar.append(
                    {
                        "day": i + 1,
                        "topics": day_topics,
                        "slots": ["morning", "evening"],
                    }
                )
            return {"success": True, "days": days, "calendar": calendar}
        except Exception as e:
            logger.error("Social calendar generation failed: %s", e)
            return {"success": False, "error": _safe_error(e), "calendar": []}

    # ──────────────────────────────────────────────
    #  Image Generation (ComfyUI + Cloud Fallback)
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_generate_image(prompt: str, **kwargs) -> dict:
        """Generate image via ComfyUI or cloud fallback.

        Tries local ComfyUI first (free, fast, full workflow control),
        then falls back to SiliconFlow/Pollinations cloud APIs.
        """
        try:
            from src.tools.comfyui_client import generate_image

            path = await generate_image(prompt, **kwargs)
            return {"success": bool(path), "path": path}
        except Exception as e:
            logger.error("Image generation RPC failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_generate_persona_photo(persona: str, scenario: str, mood: str = "natural") -> dict:
        """Generate persona-consistent photo for social media.

        Uses persona visual identity for prompt construction.
        ComfyUI local first, cloud fallback.
        """
        try:
            from src.tools.comfyui_client import generate_persona_photo

            path = await generate_persona_photo(persona, scenario, mood)
            return {"success": bool(path), "path": path}
        except Exception as e:
            logger.error("Persona photo RPC failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  Memory
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_memory_search(
        query: str,
        limit: int = 10,
        mode: str = "hybrid",
        category: Optional[str] = None,
    ) -> dict:
        """Search shared memory (hybrid / semantic / keyword).

        Returns dict with query, mode, results list, and total_count.
        """
        from src.bot.globals import shared_memory

        results: list = []
        try:
            if mode == "semantic":
                # semantic_search returns List[Dict]
                raw_list = shared_memory.semantic_search(
                    query=query,
                    limit=limit,
                    category=category,
                )
                raw_results = raw_list or []
            else:
                # search() returns Dict with "results" key
                raw_dict = shared_memory.search(
                    query=query,
                    limit=limit,
                    mode=mode,
                )
                raw_results = (raw_dict or {}).get("results", [])

            for r in raw_results:
                results.append(
                    {
                        "key": r.get("key", ""),
                        "value": r.get("value", ""),
                        "category": r.get("category", ""),
                        "importance": r.get("importance", 1),
                        "access_count": r.get("access_count", 0),
                        "similarity": r.get("similarity", r.get("score", 0.0)),
                        "match_type": r.get("match_type", ""),
                        "source_bot": r.get("source_bot", ""),
                    }
                )
        except Exception as e:
            logger.warning("Memory search failed: %s", e)

        return {
            "query": query,
            "mode": mode,
            "results": results,
            "total_count": len(results),
        }

    @staticmethod
    def _rpc_memory_stats() -> dict:
        """Get memory system statistics."""
        from src.bot.globals import shared_memory

        _empty = {
            "total_entries": 0,
            "by_category": {},
            "total_relations": 0,
            "avg_importance": 0.0,
            "engine": "sqlite",
        }
        try:
            stats = shared_memory.get_stats()
            return {
                "total_entries": stats.get("total_entries", 0),
                "by_category": stats.get("by_category", {}),
                "total_relations": stats.get("total_relations", 0),
                "avg_importance": stats.get("avg_importance", 0.0),
                "engine": stats.get("engine", "sqlite"),
            }
        except Exception as e:
            logger.warning("Failed to get memory stats: %s", e)
            return _empty

    @staticmethod
    def _rpc_memory_delete(key: str) -> dict:
        """Delete a memory entry by key."""
        from src.bot.globals import shared_memory

        try:
            result = shared_memory.forget(key)
            if result.get("success"):
                return {"success": True, "deleted": result.get("deleted", 1), "key": key}
            return {"success": False, "error": result.get("error", f"未找到: {key}")}
        except Exception as e:
            logger.warning("Memory delete failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_memory_update(key: str, value: str) -> dict:
        """Update a memory entry value by re-writing the same key."""
        from src.bot.globals import shared_memory

        try:
            search_result = shared_memory.search(key, limit=20)
            existing = next(
                (item for item in (search_result or {}).get("results", []) if item.get("key") == key),
                None,
            )
            if not existing:
                return {"success": False, "error": f"未找到: {key}"}

            remember_result = shared_memory.remember(
                key=key,
                value=value,
                category=existing.get("category") or "general",
                source_bot=existing.get("source_bot") or "manager",
                importance=int(existing.get("importance", 1) or 1),
            )
            return {
                "success": bool(remember_result.get("success", False)),
                "key": key,
                "value": value,
            }
        except Exception as e:
            logger.warning("Memory update failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  API Pool
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_pool_stats() -> dict:
        """Get free API pool (LiteLLM router) statistics.

        额外注入 today_cost / week_cost / month_cost / budget 字段，
        供前端 AIConfig 面板展示成本统计。
        """
        from src.litellm_router import free_pool

        try:
            stats = free_pool.get_stats()
        except Exception as e:
            logger.warning("Failed to get pool stats: %s", e)
            stats = {}

        # 注入成本统计字段（从 CostAnalyzer 读取）
        try:
            from src.monitoring import cost_analyzer
            # 今日成本：最近 24 小时
            daily_data = cost_analyzer.analyze_by_bot(hours=24)
            stats["today_cost"] = round(
                sum(v.get("cost_usd", 0) for v in daily_data.values()), 4
            )
            # 本周成本：最近 7 天
            weekly_data = cost_analyzer.analyze_by_bot(hours=168)
            stats["week_cost"] = round(
                sum(v.get("cost_usd", 0) for v in weekly_data.values()), 4
            )
            # 本月成本：最近 30 天
            monthly_data = cost_analyzer.analyze_by_bot(hours=720)
            stats["month_cost"] = round(
                sum(v.get("cost_usd", 0) for v in monthly_data.values()), 4
            )
        except Exception as e:
            logger.warning("注入成本统计失败，使用默认值: %s", e)
            stats.setdefault("today_cost", 0.0)
            stats.setdefault("week_cost", 0.0)
            stats.setdefault("month_cost", 0.0)

        # 注入预算字段（从环境变量或 CostController 读取）
        try:
            import os
            # 日预算 * 30 = 月预算估算
            daily_budget = float(os.environ.get("OMEGA_DAILY_BUDGET", "50.0"))
            stats["budget"] = round(daily_budget * 30, 2)
        except Exception:
            stats.setdefault("budget", 0.0)

        return stats

    # ──────────────────────────────────────────────
    #  Metrics
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_prometheus_metrics() -> str:
        """Get Prometheus metrics in text exposition format."""
        from src.monitoring import prom

        try:
            return prom.render()
        except Exception as e:  # noqa: F841
            return ""

    # ──────────────────────────────────────────────
    #  Shopping — 比价引擎
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_compare_prices(
        query: str,
        limit_per_platform: int = 5,
        use_ai_summary: bool = True,
    ) -> dict:
        """Compare prices across multiple platforms.

        搬运 什么值得买 + 京东公开搜索 + AI 分析总结。
        Layer 4 (商务层) gap fill — no login required.
        """
        from src.shopping.price_engine import compare_prices

        try:
            report = await compare_prices(
                query,
                use_ai_summary=use_ai_summary,
                limit_per_platform=limit_per_platform,
            )
            return {
                "success": True,
                "query": report.query,
                "results": report.results,
                "best_deal": report.best_deal,
                "ai_summary": report.ai_summary,
                "platforms": report.searched_platforms,
                "count": len(report.results),
            }
        except Exception as e:
            logger.error("Price comparison failed for '%s': %s", query, e)
            return {"success": False, "error": _safe_error(e)}
