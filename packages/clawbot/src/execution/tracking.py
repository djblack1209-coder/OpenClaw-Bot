"""
Execution — 社交分析与价格追踪
包含社媒互动数据、粉丝增长、策略评估、商品比价监控等功能。
从 life_automation.py 拆分以改善可维护性。

> 最后更新: 2026-03-28
"""
import logging

from src.execution._db import get_conn
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

def record_post_engagement(draft_id: int, platform: str, likes: int = 0,
                           comments: int = 0, shares: int = 0, views: int = 0,
                           post_url: str = "", db_path=None) -> bool:
    """记录帖子的互动数据"""
    # 输入验证
    likes = max(0, int(likes or 0))
    comments = max(0, int(comments or 0))
    shares = max(0, int(shares or 0))
    views = max(0, int(views or 0))
    _valid_platforms = {"x", "xhs", "weibo", "linkedin", "douyin", "bilibili"}
    if platform not in _valid_platforms:
        return {"success": False, "error": f"不支持的平台: {platform}"}
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO post_engagement (draft_id, platform, post_url, likes, comments, shares, views) "
                "VALUES (?,?,?,?,?,?,?)",
                (draft_id, platform, post_url, likes, comments, shares, views),
            )
        return True
    except Exception as e:
        logger.error(f"[Engagement] 记录失败: {scrub_secrets(str(e))}")
        return False


def get_engagement_summary(days: int = 7, db_path=None) -> dict:
    """获取近N天帖子互动汇总"""
    import time
    cutoff = time.time() - days * 86400
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT platform, SUM(likes), SUM(comments), SUM(shares), SUM(views), COUNT(*) "
                "FROM post_engagement WHERE checked_at > ? GROUP BY platform",
                (cutoff,),
            ).fetchall()
        platforms = {}
        for r in rows:
            likes = r[1] or 0
            comments = r[2] or 0
            shares = r[3] or 0
            views = r[4] or 0
            posts = r[5] or 0
            engagement_rate = round((likes + comments + shares) / max(views, 1) * 100, 2)
            platforms[r[0]] = {
                "likes": likes, "comments": comments,
                "shares": shares, "views": views, "posts": posts,
                "engagement_rate": engagement_rate,
            }
        total_likes = sum(p["likes"] for p in platforms.values())
        total_posts = sum(p["posts"] for p in platforms.values())
        return {"success": True, "days": days, "platforms": platforms,
                "total_likes": total_likes, "total_posts": total_posts}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────── 粉丝增长时序 ───────────

def record_follower_snapshot(platform: str, followers: int, following: int = 0,
                             total_likes: int = 0, total_views: int = 0,
                             db_path=None) -> bool:
    """记录粉丝数快照 — 每天每平台一条，用 INSERT OR REPLACE 保证唯一性"""
    _valid = {"x", "xhs", "weibo", "linkedin", "douyin", "bilibili"}
    if platform not in _valid:
        logger.warning("[FollowerSnapshot] 不支持的平台: %s", platform)
        return False
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO follower_snapshots "
                "(platform, followers, following, total_likes, total_views, snapshot_at) "
                "VALUES (?, ?, ?, ?, ?, strftime('%s','now'))",
                (platform, max(0, int(followers)), max(0, int(following)),
                 max(0, int(total_likes)), max(0, int(total_views))),
            )
        logger.info("[FollowerSnapshot] %s: followers=%d", platform, followers)
        return True
    except Exception as e:
        logger.error("[FollowerSnapshot] 存储失败: %s", e)
        return False


def get_follower_growth(days: int = 7, db_path=None) -> dict:
    """获取粉丝增长数据 — 返回各平台的起止粉丝数和净增长

    返回格式:
        {
            "x":   {"start": 1200, "end": 1350, "change": 150, "change_pct": 12.5},
            "xhs": {"start": 500,  "end": 580,  "change": 80,  "change_pct": 16.0},
        }
    """
    import time
    cutoff = time.time() - days * 86400
    result = {}
    try:
        with get_conn(db_path) as conn:
            # 查找 cutoff 之后每个平台最早和最晚的快照
            rows = conn.execute(
                "SELECT platform, "
                "  MIN(CASE WHEN snapshot_at = earliest THEN followers END) AS start_f, "
                "  MAX(CASE WHEN snapshot_at = latest  THEN followers END) AS end_f "
                "FROM follower_snapshots "
                "INNER JOIN ("
                "  SELECT platform AS p, MIN(snapshot_at) AS earliest, MAX(snapshot_at) AS latest "
                "  FROM follower_snapshots WHERE snapshot_at > ? GROUP BY platform"
                ") sub ON follower_snapshots.platform = sub.p "
                "  AND snapshot_at IN (earliest, latest) "
                "WHERE snapshot_at > ? "
                "GROUP BY platform",
                (cutoff, cutoff),
            ).fetchall()

            for plat, start_f, end_f in rows:
                start_f = start_f or 0
                end_f = end_f or 0
                change = end_f - start_f
                change_pct = round(change / max(start_f, 1) * 100, 1)
                result[plat] = {
                    "start": start_f,
                    "end": end_f,
                    "change": change,
                    "change_pct": change_pct,
                }
    except Exception as e:
        logger.error("[FollowerGrowth] 查询失败: %s", e)
    return result


# ─────────── 策略绩效感知 ───────────

def evaluate_strategy_performance(days: int = 30) -> dict:
    """评估近N天各策略的简易绩效 — 复用 TradingJournal 已有的 get_performance 方法"""
    try:
        from src.trading_journal import journal
        perf = journal.get_performance(days=days)
        total = perf.get("total_trades", 0)
        if total == 0:
            return {"success": False, "reason": "无近期交易数据"}

        win_rate = perf.get("win_rate", 0) or 0
        # 自动检测: >1 说明是百分比格式，需要转换
        if win_rate > 1:
            win_rate = win_rate / 100
        # 此时 win_rate 一定是 0~1 的小数
        total_pnl = perf.get("total_pnl", 0)
        wins = int(total * win_rate)
        losses = total - wins

        # 根据绩效数据给出操作建议
        if win_rate >= 0.6:
            suggestion = "策略表现优秀，维持当前权重"
        elif win_rate >= 0.5:
            suggestion = "策略表现正常，维持当前策略"
        elif win_rate >= 0.4:
            suggestion = "胜率偏低，建议适当降低仓位"
        else:
            suggestion = "胜率过低，建议暂停自动交易并复盘"

        return {
            "success": True,
            "days": days,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 3),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": perf.get("profit_factor", 0),
            "max_drawdown": perf.get("max_drawdown", 0),
            "sharpe": round(perf.get("sharpe", 0), 2),
            "suggestion": suggestion,
        }
    except ImportError:
        return {"success": False, "reason": "trading_journal 模块不可用"}
    except Exception as e:
        return {"success": False, "reason": str(e)}


# ─────────── 账单追踪 (话费/水电费余额检测提醒) ───────────


MAX_PRICE_WATCHES_PER_USER = 10


def add_price_watch(user_id, chat_id, keyword, target_price,
                    platform="all", db_path=None) -> dict:
    """添加降价监控 — 返回 watch_id

    用户说 "帮我盯着AirPods，降到800以下告诉我" 就会调用此函数。
    """
    # 参数校验
    keyword = str(keyword or "").strip()
    if not keyword or len(keyword) > 100:
        return {"success": False, "error": "商品关键词不能为空且不超过100字"}
    target_price = float(target_price)
    if target_price <= 0 or target_price > 1_000_000:
        return {"success": False, "error": "目标价格无效，请输入 0.01 ~ 1,000,000"}
    try:
        with get_conn(db_path) as conn:
            # 检查用户活跃监控数量上限
            count = conn.execute(
                "SELECT COUNT(*) FROM price_watches "
                "WHERE user_id=? AND status='active'",
                (str(user_id),),
            ).fetchone()[0]
            if count >= MAX_PRICE_WATCHES_PER_USER:
                return {
                    "success": False,
                    "error": f"最多只能同时监控 {MAX_PRICE_WATCHES_PER_USER} 个商品",
                }
            cursor = conn.execute(
                "INSERT INTO price_watches "
                "(user_id, chat_id, keyword, target_price, platform) "
                "VALUES (?,?,?,?,?)",
                (str(user_id), str(chat_id), keyword,
                 target_price, platform or "all"),
            )
            return {
                "success": True,
                "watch_id": cursor.lastrowid,
                "keyword": keyword,
                "target_price": target_price,
                "platform": platform,
            }
    except Exception as e:
        logger.error("[PriceWatch] 添加监控失败: %s", e)
        return {"success": False, "error": str(e)}


def list_price_watches(user_id, db_path=None) -> list:
    """列出用户的降价监控 — 返回活跃的监控列表"""
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT id, keyword, target_price, current_price, "
                "lowest_price, platform, status, created_at, last_checked "
                "FROM price_watches "
                "WHERE user_id=? AND status IN ('active', 'paused') "
                "ORDER BY id ASC",
                (str(user_id),),
            ).fetchall()
            return [
                {
                    "id": r[0], "keyword": r[1], "target_price": r[2],
                    "current_price": r[3], "lowest_price": r[4],
                    "platform": r[5], "status": r[6],
                    "created_at": r[7], "last_checked": r[8],
                }
                for r in rows
            ]
    except Exception as e:  # noqa: F841
        return []


def remove_price_watch(watch_id, user_id, db_path=None) -> bool:
    """删除降价监控（软删除: 改状态为 cancelled）"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "UPDATE price_watches SET status='cancelled' "
                "WHERE id=? AND user_id=? AND status='active'",
                (watch_id, str(user_id)),
            )
            return cursor.rowcount > 0
    except Exception as e:
        logger.error("[PriceWatch] 删除监控失败: %s", e)
        return False


async def check_price_watches(notify_func=None, db_path=None) -> int:
    """定时检查所有活跃监控的价格变化 — 发现降价则通知用户

    逻辑:
    1. 查询所有 status='active' 的监控
    2. 对每个监控，调用 compare_prices(keyword) 获取当前最低价
    3. 更新 current_price 和 lowest_price
    4. 如果 current_price <= target_price:
       - 状态改为 triggered
       - 调用 notify_func 发送降价通知

    返回: 本次触发的降价通知数量
    """
    import asyncio as _asyncio
    import time as _time

    triggered_count = 0
    try:
        # 获取所有活跃监控
        with get_conn(db_path) as conn:
            watches = conn.execute(
                "SELECT id, user_id, chat_id, keyword, target_price, "
                "current_price, lowest_price "
                "FROM price_watches WHERE status='active'"
            ).fetchall()

        if not watches:
            return 0

        logger.info("[PriceWatch] 开始检查 %d 个活跃监控", len(watches))

        # 使用统一比价引擎，fast_mode=True 只走 SMZDM+JD（不消耗 API 额度）
        from src.shopping.price_engine import smart_compare_prices

        for watch in watches:
            wid, user_id, chat_id, keyword, target, old_price, lowest = watch
            try:
                # 调用统一比价引擎（fast_mode=True: 只用 SMZDM+JD 爬取，速度快不消耗 API）
                report = await smart_compare_prices(
                    keyword, use_ai_summary=False, fast_mode=True,
                    limit_per_platform=3,
                )
                # 从结果中提取最低价
                best = report.best_deal
                if not best or best.get("price", 0) <= 0:
                    # 没找到有效价格，跳过但更新检查时间
                    with get_conn(db_path) as conn:
                        conn.execute(
                            "UPDATE price_watches SET last_checked=? WHERE id=?",
                            (_time.time(), wid),
                        )
                    await _asyncio.sleep(3)  # 防反爬间隔
                    continue

                new_price = best["price"]
                new_lowest = min(lowest, new_price) if lowest > 0 else new_price
                now_ts = _time.time()

                # 判断是否达到目标价
                if new_price <= target:
                    # 降价触发！
                    with get_conn(db_path) as conn:
                        conn.execute(
                            "UPDATE price_watches SET current_price=?, "
                            "lowest_price=?, last_checked=?, "
                            "status='triggered', triggered_at=? WHERE id=?",
                            (new_price, new_lowest, now_ts, now_ts, wid),
                        )
                    triggered_count += 1

                    # 发送降价通知
                    if notify_func:
                        platform_info = best.get("platform", "")
                        title_info = best.get("title", keyword)[:50]
                        msg = (
                            f"🔔 降价提醒！\n\n"
                            f"📦 {title_info}\n"
                            f"💰 当前价: ¥{new_price}\n"
                            f"🎯 目标价: ¥{target}\n"
                            f"📉 已降到目标价以下！\n"
                        )
                        if platform_info:
                            msg += f"🏪 平台: {platform_info}\n"
                        url = best.get("url", "")
                        if url:
                            msg += f"🔗 链接: {url}\n"
                        msg += "\n💡 此监控已自动停止，如需继续可重新添加"
                        try:
                            await notify_func(msg, chat_id=int(chat_id))
                        except Exception as e:
                            logger.warning("[PriceWatch] 通知发送失败: %s", e)
                else:
                    # 未达目标价，仅更新价格数据
                    with get_conn(db_path) as conn:
                        conn.execute(
                            "UPDATE price_watches SET current_price=?, "
                            "lowest_price=?, last_checked=? WHERE id=?",
                            (new_price, new_lowest, now_ts, wid),
                        )

                # 防反爬: 每次查询间隔 3 秒
                await _asyncio.sleep(3)

            except Exception as e:
                logger.warning("[PriceWatch] 检查 #%d (%s) 失败: %s", wid, keyword, e)
                continue

        logger.info("[PriceWatch] 检查完成, %d 个触发降价通知", triggered_count)

    except Exception as e:
        logger.error("[PriceWatch] 批量检查异常: %s", e)

    return triggered_count


# ─────────── 数据生命周期清理 ───────────

def cleanup_stale_watches(days_triggered=30, days_expired=90, db_path=None):
    """清理过期的降价监控和账单追踪

    三项清理:
    1. 已触发/已取消超过 days_triggered 天的降价监控 → 永久删除
    2. 已删除超过 days_triggered 天的账单追踪 → 永久删除
    3. active 但超过 days_expired 天未检查的降价监控 → 标记为 expired

    Returns:
        dict: 各项清理的行数统计
    """
    import time as _time

    result = {
        "price_watches_purged": 0,
        "price_watches_expired": 0,
        "bill_accounts_purged": 0,
    }
    now_ts = _time.time()

    try:
        with get_conn(db_path) as conn:
            # 1. 清理已触发/已取消超过 N 天的降价监控（硬删除）
            cutoff_triggered = now_ts - days_triggered * 86400
            try:
                cursor = conn.execute(
                    "DELETE FROM price_watches "
                    "WHERE status IN ('triggered', 'cancelled') "
                    "AND COALESCE(triggered_at, created_at) < ?",
                    (cutoff_triggered,),
                )
                result["price_watches_purged"] = cursor.rowcount
            except Exception as e:
                logger.debug("[Cleanup] 清理降价监控失败: %s", e)

            # 2. 清理已删除超过 N 天的账单追踪（硬删除）
            try:
                cursor = conn.execute(
                    "DELETE FROM bill_accounts "
                    "WHERE status = 'deleted' "
                    "AND last_updated < ?",
                    (cutoff_triggered,),
                )
                result["bill_accounts_purged"] = cursor.rowcount
            except Exception as e:
                logger.debug("[Cleanup] 清理账单追踪失败: %s", e)

            # 3. 超过 N 天未更新的 active 降价监控 → 标记为 expired
            cutoff_expired = now_ts - days_expired * 86400
            try:
                cursor = conn.execute(
                    "UPDATE price_watches SET status = 'expired' "
                    "WHERE status = 'active' "
                    "AND last_checked > 0 AND last_checked < ?",
                    (cutoff_expired,),
                )
                result["price_watches_expired"] = cursor.rowcount
            except Exception as e:
                logger.debug("[Cleanup] 标记过期监控失败: %s", e)

    except Exception as e:
        logger.error("[Cleanup] 数据生命周期清理异常: %s", e)

    total = sum(result.values())
    if total > 0:
        logger.info(
            "[Cleanup] 数据清理: 删除监控=%d, 过期监控=%d, 删除账单=%d",
            result["price_watches_purged"],
            result["price_watches_expired"],
            result["bill_accounts_purged"],
        )
    return result
