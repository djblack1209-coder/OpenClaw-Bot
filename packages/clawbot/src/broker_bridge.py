"""
ClawBot IBKR 券商桥接层 v1.0
通过 ib_async 对接盈透证券 Paper Trading（ib_insync 社区接力 fork）
- 异步下单（买入/卖出）
- 实时持仓查询
- 订单状态跟踪
- 账户资金查询
- 自动重连机制
"""

import asyncio
import json
import logging
import os as _os
import shlex
import time as _time
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING
from datetime import datetime

from src.notify_style import format_ibkr_connectivity
from src.utils import now_et
from src.broker_scanner import BrokerScannerMixin
from src.broker_slippage import BrokerSlippageMixin, SlippageEstimate  # noqa: F401 — 向后兼容重导出

BUDGET_STATE_FILE = Path(__file__).parent.parent / "data" / "broker_budget_state.json"

logger = logging.getLogger(__name__)

# ============ IBKR 连接/重试时间常量（秒） ============
IBKR_CONNECT_TIMEOUT = 20  # Gateway 连接超时
IBKR_GATEWAY_LAUNCH_TIMEOUT = 150  # Gateway 自动启动命令超时（2.5分钟）
IBKR_GATEWAY_READY_WAIT = 5  # Gateway 启动成功后等待就绪
IBKR_RECONNECT_MAX_BACKOFF = 120.0  # 重连退避上限（2分钟）
IBKR_HEARTBEAT_INTERVAL = 30  # 心跳保活间隔
IBKR_RECONNECT_DEBOUNCE = 3  # 断连后重连前等待（防抖动）
IBKR_ORDER_POLL_INTERVAL = 0.5  # 订单状态轮询间隔
IBKR_CANCEL_CONFIRM_WAIT = 1  # 取消订单后等待确认

if TYPE_CHECKING:
    from ib_async import IB, MarketOrder, LimitOrder

try:
    from ib_async import IB, MarketOrder, LimitOrder

    HAS_IB = True
except ImportError:
    HAS_IB = False
    # 定义占位类型，避免类定义时 NameError
    IB = None  # type: ignore[assignment,misc]
    MarketOrder = None  # type: ignore[assignment,misc]
    LimitOrder = None  # type: ignore[assignment,misc]
    logger.warning("[IBKRBridge] ib_async 未安装，IBKR功能不可用")


class IBKRBridge(BrokerScannerMixin, BrokerSlippageMixin):
    """IBKR Paper Trading 桥接层（带预算控制 + 全自动重连 + 健康监控）"""

    def __init__(
        self, host: str = "127.0.0.1", port: int = 4002, client_id: int = 0, account: str = "", budget: float = 2000.0
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.budget = budget  # 预算上限（USD）
        self.total_spent = 0.0  # 已花费
        self.ib: Optional[IB] = None
        self._connected = False
        self._reconnect_lock = asyncio.Lock()
        self._budget_lock = asyncio.Lock()  # 预算读写原子锁，防止并发下单时预算追踪失准
        self._notify_func = None  # Telegram 通知回调，由外部注入
        self._disconnect_count = 0
        self._last_reconnect_attempt = 0.0  # 上次重连时间戳
        self._reconnect_backoff = 5.0  # 初始重连退避秒数
        self._keepalive_task = None  # 心跳保活任务
        self._auto_reconnect_task = None  # 断连自动重连任务
        # 健康度指标
        self._consecutive_pings = 0  # 连续成功心跳次数
        self._last_ping_time = 0.0  # 上次心跳时间戳
        self._last_ping_latency_ms = 0.0  # 上次心跳延迟(ms)
        self._total_reconnects = 0  # 累计重连次数
        self._connected_since = 0.0  # 本次连接建立时间
        self._autostart_attempted = False  # 防止重复启动 Gateway
        self._last_notify_state = ""  # 去重：上次通知的连接状态
        # 连接失败日志降频：避免 IBKR 未运行时 stderr 被重复错误填满
        self._consecutive_connect_failures: int = 0  # 连续连接失败计数
        self._whitelist_block_count: int = 0  # 白名单拦截次数计数

        # 启动时恢复预算状态
        self._load_budget_state()

    def _save_budget_state(self):
        """Persist daily budget state to survive restarts."""
        try:
            BUDGET_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {"date": now_et().strftime("%Y-%m-%d"), "total_spent": self.total_spent}
            BUDGET_STATE_FILE.write_text(json.dumps(state))
        except Exception as e:
            logger.warning("Failed to persist budget state: %s", e)

    def _load_budget_state(self):
        """Restore daily budget state after restart."""
        try:
            if BUDGET_STATE_FILE.exists():
                state = json.loads(BUDGET_STATE_FILE.read_text())
                if state.get("date") == now_et().strftime("%Y-%m-%d"):
                    self.total_spent = state.get("total_spent", 0.0)
                    logger.info("Restored budget state: spent $%.2f today", self.total_spent)
                else:
                    logger.info("Budget state from previous day (%s), starting fresh", state.get("date"))
        except Exception as e:
            logger.warning("Failed to load budget state: %s", e)

    def set_notify(self, func):
        """注入 Telegram 通知回调"""
        self._notify_func = func

    async def _notify_connectivity(self, state: str, title: str, detail: str):
        """连接状态通知 — 相同状态不重复推送"""
        if not self._notify_func:
            return
        if _os.getenv("IBKR_NOTIFY_CONNECTIVITY", "false").lower() not in {"1", "true", "yes", "on"}:
            return
        # 去重：相同状态不重复推
        if state == self._last_notify_state:
            logger.debug("[IBKR] 跳过重复通知: %s", state)
            return
        self._last_notify_state = state
        try:
            await self._notify_func(format_ibkr_connectivity(title, detail))
        except Exception as e:
            logger.debug("[IBKR] 通知发送失败: %s", e)

    def _notify_connectivity_sync(self, state: str, title: str, detail: str):
        """同步上下文中发送连接通知（用于 IB 回调线程）"""
        if not self._notify_func:
            return
        if _os.getenv("IBKR_NOTIFY_CONNECTIVITY", "false").lower() not in {"1", "true", "yes", "on"}:
            return
        if state == self._last_notify_state:
            return
        self._last_notify_state = state
        msg = format_ibkr_connectivity(title, detail)
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(loop.create_task, self._notify_func(msg))
        except RuntimeError:
            # 没有运行中的事件循环（IBKR 回调在独立线程中），静默跳过
            logger.debug("[IBKR] 无运行中的事件循环，断连通知跳过")

    async def connect(self) -> bool:
        """连接到 IB Gateway（带指数退避重连）"""
        if not HAS_IB:
            logger.error("[IBKR] ib_async 未安装")
            return False

        async with self._reconnect_lock:
            if self._connected and self.ib and self.ib.isConnected():
                return True

            # 指数退避：避免频繁重连冲击 Gateway
            now = _time.time()
            elapsed = now - self._last_reconnect_attempt
            if elapsed < self._reconnect_backoff:
                wait = self._reconnect_backoff - elapsed
                logger.debug("[IBKR] 重连退避中，%.1fs 后重试", wait)
                await asyncio.sleep(wait)

            self._last_reconnect_attempt = _time.time()

            # 清理旧连接
            if self.ib:
                try:
                    self.ib.disconnect()
                except Exception as e:
                    logger.debug("[IBKR] 清理旧连接异常(可忽略): %s", e)

            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    self.ib = IB()
                    # 注册断连事件回调
                    self.ib.disconnectedEvent += self._on_disconnect
                    await self.ib.connectAsync(
                        self.host,
                        self.port,
                        clientId=self.client_id,
                        readonly=False,  # 确保有下单权限
                        timeout=IBKR_CONNECT_TIMEOUT,
                    )
                    self._connected = True
                    self._disconnect_count = 0
                    self._reconnect_backoff = 5.0  # 重置退避
                    self._consecutive_pings = 0
                    self._connected_since = _time.time()
                    # 连接成功，重置失败计数器
                    if self._consecutive_connect_failures > 0:
                        logger.info(
                            "[IBKR] 连接恢复（此前连续失败 %d 次）",
                            self._consecutive_connect_failures,
                        )
                    self._consecutive_connect_failures = 0
                    accounts = self.ib.managedAccounts()
                    logger.info("[IBKR] 连接成功，账户: %s (clientId=%d)", accounts, self.client_id)

                    # 启动心跳保活
                    self._start_keepalive()

                    return True
                except Exception as e:
                    # 日志降频：根据连续失败次数决定日志级别
                    # 第 1 次失败：WARNING 完整信息
                    # 第 2-5 次：DEBUG 简短信息
                    # 第 5 次以后：每 5 次打一次 WARNING，其余 DEBUG
                    fail_count = self._consecutive_connect_failures + attempt
                    if fail_count <= 1:
                        logger.warning("[IBKR] 连接尝试 %d/%d 失败: %s", attempt, max_retries, e)
                    elif fail_count <= 5:
                        logger.debug("[IBKR] 连接尝试 %d/%d 失败: %s", attempt, max_retries, e)
                    else:
                        if fail_count % 5 == 0:
                            logger.warning(
                                "[IBKR] 连接尝试 %d/%d 失败（已连续失败 %d 次）: %s",
                                attempt,
                                max_retries,
                                fail_count,
                                e,
                            )
                        else:
                            logger.debug("[IBKR] 连接尝试 %d/%d 失败: %s", attempt, max_retries, e)
                    if attempt < max_retries:
                        backoff = 2**attempt  # 2s, 4s
                        logger.info("[IBKR] %ds 后重试...", backoff)
                        await asyncio.sleep(backoff)

            # 全部重试失败，尝试自动启动 IB Gateway
            if _os.getenv("IBKR_AUTOSTART", "").lower() in {"1", "true", "yes", "on"}:
                start_cmd = _os.getenv("IBKR_START_CMD", "")
                if start_cmd and not self._autostart_attempted:
                    # 安全修复: 校验 IBKR_START_CMD 中的可执行文件是否在白名单内
                    # 支持两种格式:
                    #   1. 直接调用: "ibgateway" / "start_ibkr_gateway.sh"
                    #   2. Shell 包装: "bash start_ibkr_gateway.sh" / "sh /path/to/script.sh"
                    _ALLOWED_GATEWAY_CMDS = frozenset(
                        {
                            "ibc",
                            "ibgateway",
                            "IBController",
                            "ibcontroller",
                            "IBGateway",
                            "start_ibkr_gateway.sh",
                        }
                    )
                    _ALLOWED_SHELLS = frozenset({"bash", "sh", "zsh"})
                    cmd_parts = shlex.split(start_cmd)
                    if not cmd_parts:
                        cmd_basename = ""
                    else:
                        first_basename = _os.path.basename(cmd_parts[0])
                        # 如果第一个 token 是 shell 解释器，检查第二个 token（实际脚本）
                        if first_basename in _ALLOWED_SHELLS and len(cmd_parts) > 1:
                            cmd_basename = _os.path.basename(cmd_parts[1])
                        else:
                            cmd_basename = first_basename
                    if not cmd_basename or cmd_basename not in _ALLOWED_GATEWAY_CMDS:
                        # 白名单拦截日志降频：首次和每 10 次打 WARNING，其余 DEBUG
                        self._whitelist_block_count += 1
                        if self._whitelist_block_count == 1 or self._whitelist_block_count % 10 == 0:
                            logger.warning(
                                "[IBKR] IBKR_START_CMD 不在白名单中，拒绝执行（第 %d 次拦截）: %s",
                                self._whitelist_block_count,
                                start_cmd[:80],
                            )
                        else:
                            logger.debug(
                                "[IBKR] IBKR_START_CMD 不在白名单中，拒绝执行（第 %d 次拦截）",
                                self._whitelist_block_count,
                            )
                    else:
                        self._autostart_attempted = True
                        logger.info("[IBKR] 连接失败，尝试自动启动 Gateway: %s", start_cmd)
                        try:
                            proc = await asyncio.create_subprocess_exec(
                                *shlex.split(start_cmd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                            )
                            stdout, stderr = await asyncio.wait_for(
                                proc.communicate(), timeout=IBKR_GATEWAY_LAUNCH_TIMEOUT
                            )
                            if proc.returncode == 0:
                                logger.info("[IBKR] Gateway 启动成功，重试连接...")
                                await asyncio.sleep(IBKR_GATEWAY_READY_WAIT)
                                # 修复死锁: asyncio.Lock 不可重入，不能递归调用 connect()
                                # 直接在锁内重试连接逻辑（只尝试一次）
                                try:
                                    self.ib = IB()
                                    self.ib.disconnectedEvent += self._on_disconnect
                                    await self.ib.connectAsync(
                                        self.host, self.port, clientId=self.client_id,
                                        readonly=False, timeout=IBKR_CONNECT_TIMEOUT,
                                    )
                                    self._connected = True
                                    self._disconnect_count = 0
                                    self._reconnect_backoff = 5.0
                                    self._consecutive_pings = 0
                                    self._connected_since = _time.time()
                                    self._consecutive_connect_failures = 0
                                    accounts = self.ib.managedAccounts()
                                    logger.info("[IBKR] Gateway 启动后连接成功，账户: %s", accounts)
                                    self._start_keepalive()
                                    return True
                                except Exception as retry_e:
                                    logger.warning("[IBKR] Gateway 启动后连接仍失败: %s", retry_e)
                            else:
                                logger.warning(
                                    "[IBKR] Gateway 启动失败: rc=%d, %s", proc.returncode, stderr.decode()[:200]
                                )
                        except Exception as e:
                            logger.warning("[IBKR] Gateway 自动启动异常: %s", e)

            # 增加退避时间（最大 120s）
            self._reconnect_backoff = min(self._reconnect_backoff * 2, IBKR_RECONNECT_MAX_BACKOFF)
            self._consecutive_connect_failures += max_retries
            # 日志降频：首次失败打 ERROR，后续降为 WARNING/DEBUG
            if self._consecutive_connect_failures <= max_retries:
                logger.error(
                    "[IBKR] 连接失败（已重试%d次），下次退避%.0fs",
                    max_retries,
                    self._reconnect_backoff,
                )
            elif self._consecutive_connect_failures % 15 == 0:
                # 每 15 次累计失败打一次 WARNING，提醒用户 Gateway 仍未启动
                logger.warning(
                    "[IBKR] 连接持续失败（累计 %d 次），Gateway 可能未运行，退避%.0fs",
                    self._consecutive_connect_failures,
                    self._reconnect_backoff,
                )
            else:
                logger.debug(
                    "[IBKR] 连接失败（累计 %d 次），退避%.0fs",
                    self._consecutive_connect_failures,
                    self._reconnect_backoff,
                )
            self._connected = False
            return False

    async def ensure_connected(self) -> bool:
        """确保连接，断开则自动重连"""
        if self.ib and self.ib.isConnected():
            return True
        # 日志降频：首次断连打 INFO，后续打 DEBUG
        if self._consecutive_connect_failures == 0:
            logger.info("[IBKR] 连接已断开，尝试重连...")
        else:
            logger.debug("[IBKR] 连接已断开，尝试重连（累计失败 %d 次）...", self._consecutive_connect_failures)
        return await self.connect()

    def _start_keepalive(self):
        """启动心跳保活任务 — 每 30s 发一次轻量请求防止 Gateway 断连"""
        if self._keepalive_task and not self._keepalive_task.done():
            return  # 已在运行

        async def _keepalive_loop():
            while self._connected and self.ib:
                try:
                    await asyncio.sleep(IBKR_HEARTBEAT_INTERVAL)
                    if self.ib and self.ib.isConnected():
                        t0 = _time.time()
                        # 用底层 client 发送原始 reqCurrentTime 包
                        # 不阻塞事件循环（避免 "event loop already running"）
                        self.ib.client.reqCurrentTime()
                        latency = (_time.time() - t0) * 1000
                        self._consecutive_pings += 1
                        self._last_ping_time = _time.time()
                        self._last_ping_latency_ms = latency
                        # 每 10 次心跳输出一次 INFO（约 5 分钟一次）
                        if self._consecutive_pings % 10 == 1:
                            uptime_min = (_time.time() - self._connected_since) / 60
                            logger.info(
                                "[IBKR] 心跳 #%d OK (%.0fms) | 连续运行 %.0f分钟",
                                self._consecutive_pings,
                                latency,
                                uptime_min,
                            )
                        else:
                            logger.debug("[IBKR] keepalive #%d OK (%.0fms)", self._consecutive_pings, latency)
                    else:
                        logger.warning("[IBKR] 心跳检测到连接断开，触发自动重连")
                        self._connected = False
                        self._schedule_auto_reconnect()
                        break
                except asyncio.CancelledError as e:  # noqa: F841
                    break
                except Exception as e:
                    logger.warning("[IBKR] 心跳异常: %s，触发自动重连", e)
                    self._connected = False
                    self._schedule_auto_reconnect()
                    break

        try:
            loop = asyncio.get_running_loop()
            self._keepalive_task = loop.create_task(_keepalive_loop())
        except RuntimeError as e:  # noqa: F841
            pass  # 没有事件循环时跳过

    def _schedule_auto_reconnect(self):
        """断连后自动调度重连任务（不阻塞当前流程）"""
        if self._auto_reconnect_task and not self._auto_reconnect_task.done():
            return  # 已有重连任务在跑

        async def _auto_reconnect():
            await asyncio.sleep(IBKR_RECONNECT_DEBOUNCE)  # 等一下再重连，避免瞬间抖动
            # 自动重连日志降频：首次打 INFO，后续打 DEBUG
            if self._consecutive_connect_failures <= 3:
                logger.info("[IBKR] 自动重连开始...")
            else:
                logger.debug("[IBKR] 自动重连开始（累计失败 %d 次）...", self._consecutive_connect_failures)
            success = await self.connect()
            self._total_reconnects += 1
            if success:
                logger.info("[IBKR] 自动重连成功 (累计重连 %d 次)", self._total_reconnects)
                await self._notify_connectivity(
                    "reconnected", "IBKR 自动重连成功", f"累计重连 {self._total_reconnects} 次"
                )
            else:
                # 自动重连失败日志降频：首次打 ERROR，后续由 connect() 方法控制
                if self._consecutive_connect_failures <= 3:
                    logger.error("[IBKR] 自动重连失败，将在下次操作时重试")
                else:
                    logger.debug(
                        "[IBKR] 自动重连失败（累计 %d 次），将在下次操作时重试", self._consecutive_connect_failures
                    )

        try:
            loop = asyncio.get_running_loop()
            self._auto_reconnect_task = loop.create_task(_auto_reconnect())
        except RuntimeError as e:
            logger.debug("[IBKR] 无事件循环，跳过自动重连调度")

    def _on_disconnect(self):
        """IB Gateway 断连事件回调 — 自动触发重连"""
        self._connected = False
        self._disconnect_count += 1
        self._consecutive_pings = 0
        # 停止心跳保活
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        logger.warning("[IBKR] 连接断开 (第%d次)，将自动重连", self._disconnect_count)
        # 通知 + 自动重连
        self._notify_connectivity_sync(
            "disconnected", "IBKR 连接断开", f"第{self._disconnect_count}次断开，3 秒后自动重连"
        )
        # 触发自动重连
        self._schedule_auto_reconnect()

    def disconnect(self):
        """断开连接"""
        # 停止心跳保活
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        # 停止自动重连
        if self._auto_reconnect_task and not self._auto_reconnect_task.done():
            self._auto_reconnect_task.cancel()
        if self.ib:
            try:
                self.ib.disconnect()
            except Exception as e:
                logger.debug("[IBKR] 断开连接异常(可忽略): %s", e)
            self._connected = False

    # ============ 账户信息 ============

    async def get_account_summary(self) -> Dict:
        """获取账户摘要"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            summary = self.ib.accountSummary(account=self.account)
            result = {}
            for item in summary:
                if item.tag in (
                    "NetLiquidation",
                    "TotalCashValue",
                    "BuyingPower",
                    "GrossPositionValue",
                    "AvailableFunds",
                    "UnrealizedPnL",
                    "RealizedPnL",
                ):
                    result[item.tag] = {"value": float(item.value) if item.value else 0, "currency": item.currency}
            return result
        except Exception as e:
            logger.exception("获取账户摘要失败")
            return {"error": f"获取账户摘要失败: {e}"}

    async def get_account_value(self) -> str:
        """获取账户资金概览（格式化文本）"""
        summary = await self.get_account_summary()
        if "error" in summary:
            return summary["error"]

        lines = ["IBKR 模拟账户 (%s)\n" % self.account]
        tag_names = {
            "NetLiquidation": "净清算价值",
            "TotalCashValue": "现金余额",
            "BuyingPower": "购买力",
            "GrossPositionValue": "持仓市值",
            "AvailableFunds": "可用资金",
            "UnrealizedPnL": "未实现盈亏",
            "RealizedPnL": "已实现盈亏",
        }
        for tag, info in summary.items():
            name = tag_names.get(tag, tag)
            val = info["value"]
            cur = info["currency"]
            if abs(val) > 1000:
                lines.append(f"{name}: {val:,.2f} {cur}")
            else:
                lines.append(f"{name}: {val:.2f} {cur}")
        return "\n".join(lines)

    # ============ 持仓查询 ============

    async def get_positions(self) -> List[Dict]:
        """获取所有持仓"""
        if not await self.ensure_connected():
            return []

        try:
            positions = self.ib.positions(account=self.account)
            result = []
            for pos in positions:
                result.append(
                    {
                        "symbol": pos.contract.symbol,
                        "sec_type": pos.contract.secType,
                        "exchange": pos.contract.exchange,
                        "currency": pos.contract.currency,
                        "quantity": float(pos.position),
                        "avg_cost": float(pos.avgCost),
                        "market_value": float(pos.position) * float(pos.avgCost),  # 成本基础（IBKR 不直接提供实时市值）
                        "cost_basis": float(pos.position) * float(pos.avgCost),
                    }
                )
            return result
        except Exception as e:
            logger.error(f"[IBKR] 获取持仓失败: {e}")
            return []

    async def get_positions_text(self) -> str:
        """获取持仓（格式化文本）"""
        positions = await self.get_positions()
        if not positions:
            return "IBKR 持仓: 空"

        lines = [f"IBKR 持仓 ({len(positions)}个)\n"]
        for pos in positions:
            sign = "+" if pos["quantity"] > 0 else ""
            lines.append(f"{pos['symbol']}: {sign}{pos['quantity']:.0f}股 @ {pos['avg_cost']:.2f} {pos['currency']}")
        return "\n".join(lines)

    # ============ 下单 ============

    async def _place_order(
        self,
        side: str,
        symbol: str,
        quantity: float,
        order_type: str = "MKT",
        limit_price: float = 0,
        decided_by: str = "",
        reason: str = "",
    ) -> Dict:
        """统一下单逻辑（BUY/SELL 共用）"""
        if quantity <= 0:
            return {"error": f"数量必须大于零 (got {quantity})"}
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        # 买入时检查预算（加锁保证原子读取）
        if side == "BUY":
            async with self._budget_lock:
                remaining = self.budget - self.total_spent
            if remaining <= 0:
                return {"error": "预算已用完 ($%.2f/$%.2f)" % (self.total_spent, self.budget)}

        try:
            contract = self._make_contract(symbol)
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                return {"error": f"无法识别合约: {symbol}"}

            if order_type == "LMT" and limit_price > 0:
                order = LimitOrder(side, quantity, limit_price)
            else:
                order = MarketOrder(side, quantity)

            order.account = self.account
            trade = self.ib.placeOrder(contract, order)

            # P0#7: 市价单等待更长时间(30s)，限价单等确认提交后再多等5s捕获快速成交
            max_wait = 60 if order_type != "LMT" else 40
            lmt_submitted = False
            for _ in range(max_wait):
                await asyncio.sleep(IBKR_ORDER_POLL_INTERVAL)
                if trade.orderStatus.status == "Filled":
                    break
                if trade.orderStatus.status in ("Submitted", "PreSubmitted") and order_type == "LMT":
                    if not lmt_submitted:
                        lmt_submitted = True
                        # 限价单已提交，再等10秒看是否快速成交
                    elif lmt_submitted and _ >= 20:
                        # 已等10秒仍未成交，退出（后续由持仓监控跟踪）
                        break

            status = trade.orderStatus.status
            filled_qty = trade.orderStatus.filled
            avg_price = trade.orderStatus.avgFillPrice
            order_id = trade.order.orderId

            logger.info(
                "[IBKR] %s %s x%s -> %s (filled=%s @ %s)", side, symbol, quantity, status, filled_qty, avg_price
            )

            # 预算追踪（加锁保证 read-modify-write 原子性）
            if filled_qty > 0 and avg_price > 0:
                if side == "BUY":
                    async with self._budget_lock:
                        self.total_spent += filled_qty * avg_price
                        self._save_budget_state()
                    # 滑点估算日志（仅买入）
                    try:
                        slippage_est = await self.estimate_slippage(symbol, quantity, side="BUY")
                        logger.info(
                            "[IBKR] %s 滑点估算: slippage=%.2f%%, liquidity=%s, est_fill=$%.2f",
                            symbol,
                            slippage_est.estimated_slippage_pct,
                            slippage_est.liquidity_score,
                            slippage_est.estimated_fill_price,
                        )
                    except Exception as e:
                        logger.debug("[IBKR] 滑点估算跳过: %s", e)
                else:
                    # 卖出：按买入成本释放预算（而非卖出收入，避免盈亏扭曲预算）
                    # 尝试从持仓获取买入成本，回退到卖出价
                    entry_cost = filled_qty * avg_price  # 默认用卖出价
                    try:
                        positions = self.ib.positions() if self.ib else []
                        for pos in positions:
                            if pos.contract.symbol == symbol:
                                if pos.avgCost > 0:
                                    entry_cost = filled_qty * pos.avgCost
                                break
                    except Exception as e:
                        logger.warning("[IBKR] 获取 %s 成本基准失败，使用卖出价计算预算: %s", symbol, e)
                    async with self._budget_lock:
                        self.total_spent = max(0, self.total_spent - entry_cost)
                        self._save_budget_state()
                    logger.info(
                        "[IBKR] 预算释放 $%.2f (成本基准)，剩余预算 $%.2f", entry_cost, self.budget - self.total_spent
                    )
            elif side == "BUY" and order_type != "LMT":
                logger.warning("[IBKR] BUY %s 市价单未成交 (status=%s)，预算未扣除", symbol, status)

            return {
                "action": side,
                "symbol": symbol.upper(),
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price if order_type == "LMT" else None,
                "status": status,
                "filled_qty": filled_qty,
                "avg_price": avg_price,
                "order_id": order_id,
                "decided_by": decided_by,
                "reason": reason,
            }
        except Exception as e:
            action_cn = "买入" if side == "BUY" else "卖出"
            logger.error("[IBKR] %s失败: %s", action_cn, e)
            return {"error": f"{action_cn}失败: {e}"}

    async def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: str = "MKT",
        limit_price: float = 0,
        decided_by: str = "",
        reason: str = "",
    ) -> Dict:
        """买入下单（带预算控制）"""
        return await self._place_order("BUY", symbol, quantity, order_type, limit_price, decided_by, reason)

    async def sell(
        self,
        symbol: str,
        quantity: float,
        order_type: str = "MKT",
        limit_price: float = 0,
        decided_by: str = "",
        reason: str = "",
    ) -> Dict:
        """卖出下单"""
        return await self._place_order("SELL", symbol, quantity, order_type, limit_price, decided_by, reason)

    # ============ 订单管理 ============

    async def get_open_orders(self) -> List[Dict]:
        """获取未完成订单"""
        if not await self.ensure_connected():
            return []

        try:
            trades = self.ib.openTrades()
            result = []
            for trade in trades:
                result.append(
                    {
                        "order_id": trade.order.orderId,
                        "symbol": trade.contract.symbol,
                        "action": trade.order.action,
                        "quantity": trade.order.totalQuantity,
                        "order_type": trade.order.orderType,
                        "limit_price": trade.order.lmtPrice,
                        "status": trade.orderStatus.status,
                        "filled": trade.orderStatus.filled,
                        "avg_price": trade.orderStatus.avgFillPrice,
                    }
                )
            return result
        except Exception as e:
            logger.error(f"[IBKR] 获取订单失败: {e}")
            return []

    async def get_trade_snapshots(self) -> List[Dict]:
        """获取当前会话内订单快照（含已提交/已成交/已取消状态）"""
        if not await self.ensure_connected():
            return []

        try:
            result = []
            for trade in self.ib.trades():
                result.append(
                    {
                        "order_id": int(getattr(trade.order, "orderId", 0) or 0),
                        "symbol": str(getattr(trade.contract, "symbol", "") or "").upper(),
                        "action": str(getattr(trade.order, "action", "") or ""),
                        "quantity": float(getattr(trade.order, "totalQuantity", 0) or 0),
                        "status": str(getattr(trade.orderStatus, "status", "") or ""),
                        "filled": float(getattr(trade.orderStatus, "filled", 0) or 0),
                        "remaining": float(getattr(trade.orderStatus, "remaining", 0) or 0),
                        "avg_price": float(getattr(trade.orderStatus, "avgFillPrice", 0) or 0),
                        "last_fill_price": float(getattr(trade.orderStatus, "lastFillPrice", 0) or 0),
                    }
                )
            return result
        except Exception as e:
            logger.error("[IBKR] 获取订单快照失败: %s", e)
            return []

    async def get_recent_fills(self, lookback_hours: int = 48) -> List[Dict]:
        """获取近期成交回报（用于与 journal 对账）"""
        if not await self.ensure_connected():
            return []

        max_lookback = max(1, int(lookback_hours or 48))
        since_ts = _time.time() - max_lookback * 3600

        def _to_epoch(raw_time) -> float:
            if raw_time is None:
                return 0.0
            if isinstance(raw_time, datetime):
                return raw_time.timestamp()
            try:
                # ib_insync 有时返回字符串时间
                return datetime.fromisoformat(str(raw_time)).timestamp()
            except Exception as e:
                logger.exception("时间戳转换失败")
                return 0.0

        fills = []
        try:
            for fill in self.ib.fills():
                execution = getattr(fill, "execution", None)
                contract = getattr(fill, "contract", None)
                if execution is None or contract is None:
                    continue

                exec_time = getattr(execution, "time", None)
                exec_ts = _to_epoch(exec_time)
                if exec_ts > 0 and exec_ts < since_ts:
                    continue

                fills.append(
                    {
                        "exec_id": str(getattr(execution, "execId", "") or ""),
                        "order_id": int(getattr(execution, "orderId", 0) or 0),
                        "symbol": str(getattr(contract, "symbol", "") or "").upper(),
                        "side": str(getattr(execution, "side", "") or "").upper(),
                        "shares": float(getattr(execution, "shares", 0) or 0),
                        "price": float(getattr(execution, "price", 0) or 0),
                        "time": str(exec_time or ""),
                        "time_ts": exec_ts,
                    }
                )

            return fills
        except Exception as e:
            logger.error("[IBKR] 获取成交回报失败: %s", e)
            return []

    async def get_orders_text(self) -> str:
        """获取订单（格式化文本）"""
        orders = await self.get_open_orders()
        if not orders:
            return "IBKR 未完成订单: 无"

        lines = [f"IBKR 未完成订单 ({len(orders)}个)\n"]
        for o in orders:
            price_info = f"限价${o['limit_price']}" if o["order_type"] == "LMT" else "市价"
            lines.append(
                f"#{o['order_id']} {o['action']} {o['symbol']} x{o['quantity']} ({price_info}) [{o['status']}]"
            )
        return "\n".join(lines)

    async def cancel_order(self, order_id: int) -> Dict:
        """取消订单"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            trades = self.ib.openTrades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    self.ib.cancelOrder(trade.order)
                    await asyncio.sleep(IBKR_CANCEL_CONFIRM_WAIT)
                    return {"order_id": order_id, "status": "cancelled"}
            return {"error": f"找不到订单 #{order_id}"}
        except Exception as e:
            logger.exception("取消订单失败: order_id=%s", order_id)
            return {"error": f"取消订单失败: {e}"}

    async def cancel_all_orders(self) -> Dict:
        """取消所有未完成订单"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            self.ib.reqGlobalCancel()
            await asyncio.sleep(IBKR_CANCEL_CONFIRM_WAIT)
            return {"status": "all_cancelled"}
        except Exception as e:
            logger.exception("取消所有订单失败")
            return {"error": f"取消所有订单失败: {e}"}

    # ============ 预算管理 ============

    def get_budget_status(self) -> str:
        """获取预算使用情况"""
        remaining = self.budget - self.total_spent
        pct = (self.total_spent / self.budget * 100) if self.budget > 0 else 0
        return ("IBKR 预算状态\n\n预算上限: $%.2f\n已使用: $%.2f (%.1f%%)\n剩余: $%.2f") % (
            self.budget,
            self.total_spent,
            pct,
            remaining,
        )

    def reset_budget(self, new_budget: float = 0.0):
        """重置预算（total_spent 归零）

        Args:
            new_budget: 新预算上限。为 0 时从环境变量 IBKR_BUDGET 读取，
                        环境变量也未设置则默认 2000 美元。
        """
        if new_budget <= 0:
            new_budget = float(_os.getenv("IBKR_BUDGET", "2000"))
        self.budget = new_budget
        self.total_spent = 0.0
        self._save_budget_state()

    async def sync_capital(self) -> float:
        """从IBKR账户同步实际可用资金，返回可用资金金额"""
        summary = await self.get_account_summary()
        if "error" in summary:
            logger.warning("[IBKR] 同步资金失败: %s", summary["error"])
            return self.budget
        available = summary.get("AvailableFunds", {}).get("value", 0)
        net_liq = summary.get("NetLiquidation", {}).get("value", 0)
        if available > 0:
            async with self._budget_lock:
                self.budget = min(available, net_liq) if net_liq > 0 else available
                self.total_spent = 0.0
                self._save_budget_state()
            logger.info("[IBKR] 资金同步: 可用=$%.2f, 净值=$%.2f, 预算设为=$%.2f", available, net_liq, self.budget)
        return self.budget

    def is_connected(self) -> bool:
        """检查IBKR是否已连接"""
        return bool(self.ib and self.ib.isConnected())

    def get_connection_status(self) -> str:
        """获取连接状态摘要（含健康度指标）"""
        if not HAS_IB:
            return "IBKR: ib_async 未安装"
        if self.is_connected():
            uptime_min = (_time.time() - self._connected_since) / 60 if self._connected_since else 0
            parts = [
                "IBKR: 已连接 (%s, clientId=%d)" % (self.account, self.client_id),
                "  连续运行: %.0f 分钟" % uptime_min,
                "  连续心跳: %d 次" % self._consecutive_pings,
                "  心跳延迟: %.0f ms" % self._last_ping_latency_ms,
                "  累计断连: %d 次" % self._disconnect_count,
                "  累计重连: %d 次" % self._total_reconnects,
            ]
            return "\n".join(parts)
        return "IBKR: 未连接 (断连%d次, 重连%d次)" % (self._disconnect_count, self._total_reconnects)


# ── 向后兼容重导出 ──────────────────────────────────────────
# 单例/选择器逻辑已迁移至 broker_selector.py
# 使用 __getattr__ 懒加载避免循环导入
def __getattr__(name):
    """向后兼容：从 broker_selector 延迟导入 get_ibkr/ibkr/get_broker"""
    if name in ("get_ibkr", "ibkr", "get_broker"):
        from src.broker_selector import get_ibkr, ibkr, get_broker  # noqa: F811

        _exports = {"get_ibkr": get_ibkr, "ibkr": ibkr, "get_broker": get_broker}
        return _exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
