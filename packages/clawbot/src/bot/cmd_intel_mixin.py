"""情报速递命令 Mixin

提供 /intel 命令和交互式菜单，用于查看全球情报、行业新闻和地区动态。
数据源: Worldmonitor API (worldmonitor.app)
"""

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot.auth import requires_auth
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)

# --- 懒加载 worldmonitor_client，避免循环导入 + 允许优雅降级 ---
_WORLDMONITOR_AVAILABLE = False
try:
    from src.tools.worldmonitor_client import (
        fetch_category_news,
        fetch_region_news,
        generate_intel_brief,
        format_intel_items,
        fetch_news_by_query,
        INDUSTRY_CATEGORIES,
        REGION_CATEGORIES,
    )
    _WORLDMONITOR_AVAILABLE = True
except ImportError:
    logger.warning("worldmonitor_client 未安装，情报功能不可用")

# --- 中文名称 → 分类键名映射（支持模糊匹配） ---
_CATEGORY_NAME_MAP = {
    "金融": "finance",
    "金融经济": "finance",
    "经济": "finance",
    "军事": "military",
    "军事安全": "military",
    "安全": "military",
    "科技": "tech",
    "科技网络": "tech",
    "技术": "tech",
    "能源": "energy",
    "能源气候": "energy",
    "气候": "energy",
    "网络安全": "cyber",
    "网安": "cyber",
    "自然灾害": "natural",
    "灾害": "natural",
    "自然": "natural",
    "地缘政治": "geopolitics",
    "地缘": "geopolitics",
    "政治": "geopolitics",
    # 英文键名也支持
    "finance": "finance",
    "military": "military",
    "tech": "tech",
    "energy": "energy",
    "cyber": "cyber",
    "natural": "natural",
    "geopolitics": "geopolitics",
    # 地区
    "北美": "north_america",
    "欧洲": "europe",
    "亚太": "asia_pacific",
    "中东": "middle_east",
    "全球": "global",
    "north_america": "north_america",
    "europe": "europe",
    "asia_pacific": "asia_pacific",
    "middle_east": "middle_east",
    "global": "global",
}


def _category_name_to_key(name: str) -> Optional[str]:
    """将中文/英文分类名称映射为分类键名

    支持模糊匹配：输入"金融"、"金融经济"、"finance" 均返回 "finance"。

    Args:
        name: 用户输入的分类名称

    Returns:
        分类键名，未匹配到返回 None
    """
    name = name.strip().lower()

    # 精确匹配
    result = _CATEGORY_NAME_MAP.get(name)
    if result:
        return result

    # 模糊匹配：检查用户输入是否是某个键的子串，或某个键是用户输入的子串
    for map_name, key in _CATEGORY_NAME_MAP.items():
        if name in map_name or map_name in name:
            return key

    return None


def _is_region_key(key: str) -> bool:
    """判断一个分类键是否属于地区分类"""
    if not _WORLDMONITOR_AVAILABLE:
        return key in ("north_america", "europe", "asia_pacific", "middle_east", "global")
    return key in REGION_CATEGORIES


def _is_industry_key(key: str) -> bool:
    """判断一个分类键是否属于行业分类"""
    if not _WORLDMONITOR_AVAILABLE:
        return key in ("finance", "military", "tech", "energy", "cyber", "natural", "geopolitics")
    return key in INDUSTRY_CATEGORIES


def _build_intel_keyboard() -> InlineKeyboardMarkup:
    """构建情报查询的 Inline 按钮键盘

    布局:
      第1行: 金融经济 | 军事安全 | 科技网络
      第2行: 能源气候 | 网络安全 | 自然灾害
      第3行: 地缘政治
      第4行: 北美 | 欧洲 | 亚太 | 中东
      第5行: 每日情报简报
    """
    keyboard = [
        # 行业分类（前3个）
        [
            InlineKeyboardButton("🏦 金融经济", callback_data="intel_cat:finance"),
            InlineKeyboardButton("🛡️ 军事安全", callback_data="intel_cat:military"),
            InlineKeyboardButton("💻 科技网络", callback_data="intel_cat:tech"),
        ],
        # 行业分类（后3个）
        [
            InlineKeyboardButton("⚡ 能源气候", callback_data="intel_cat:energy"),
            InlineKeyboardButton("🔒 网络安全", callback_data="intel_cat:cyber"),
            InlineKeyboardButton("🌊 自然灾害", callback_data="intel_cat:natural"),
        ],
        # 行业分类（最后1个）
        [
            InlineKeyboardButton("🌍 地缘政治", callback_data="intel_cat:geopolitics"),
        ],
        # 地区分类
        [
            InlineKeyboardButton("🇺🇸 北美", callback_data="intel_reg:north_america"),
            InlineKeyboardButton("🇪🇺 欧洲", callback_data="intel_reg:europe"),
            InlineKeyboardButton("🇨🇳 亚太", callback_data="intel_reg:asia_pacific"),
            InlineKeyboardButton("🌍 中东", callback_data="intel_reg:middle_east"),
        ],
        # 每日简报
        [
            InlineKeyboardButton("📋 每日情报简报", callback_data="intel_brief"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


class IntelCommandMixin:
    """情报速递命令 Mixin — 提供 /intel、/coupon、/test_token、/set_coupon_token 和交互式情报菜单"""

    @requires_auth
    @with_typing
    async def cmd_coupon(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """处理 /coupon 命令 — 手动触发微信笔笔省每日领券

        通过 mitmproxy 抓包 + API 直调方式自动领取提现免费券。
        """
        await update.message.reply_text("⏳ 正在自动领取微信提现券，请稍候...")

        try:
            from src.execution.wechat_coupon import auto_claim_coupon
            result = await auto_claim_coupon()
            await update.message.reply_text(result)
        except ImportError:
            await update.message.reply_text(
                "⚠️ 领券模块依赖 mitmproxy，请先安装：pip install mitmproxy"
            )
        except Exception as e:
            logger.error("领券命令异常: %s", e)
            await update.message.reply_text(f"❌ 领券出错: {e}")

    @requires_auth
    @with_typing
    async def cmd_test_token(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """处理 /test_token 命令 — 测试已保存的领券 token 是否仍然有效

        用于观察 token 有效期，为后续云端部署方案提供数据。
        不走 mitmproxy 流程，纯 API 调用。
        """
        try:
            from src.execution.wechat_coupon import test_saved_token
            result = await test_saved_token()
            await update.message.reply_text(result)
        except ImportError:
            await update.message.reply_text(
                "⚠️ 领券模块未就绪，请检查 wechat_coupon 模块"
            )
        except Exception as e:
            logger.error("测试 token 异常: %s", e)
            await update.message.reply_text(f"❌ 测试出错: {e}")

    @requires_auth
    async def cmd_set_coupon_token(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """处理 /set_coupon_token 命令 — 手动设置领券 token

        用户通过手机抓包工具获取 token 后，可直接设置到系统中，
        无需走 mitmproxy + 微信桌面版的流程。
        用法: /set_coupon_token <token值>
        """
        # 从命令参数中获取 token
        if not context.args:
            await update.message.reply_text(
                "用法: /set_coupon_token <token值>\n\n"
                "token 获取方法:\n"
                "1. 手机安装抓包工具（推荐 Stream/HTTP Catcher）\n"
                "2. 打开微信「笔笔省」小程序\n"
                "3. 在抓包记录中找 discount.wxpapp.wechatpay.cn 的请求\n"
                "4. 复制请求头里的 session-token 值\n"
                "5. 发送: /set_coupon_token 你复制的token"
            )
            return

        token = context.args[0]

        try:
            from src.execution.wechat_coupon import set_token_manual
            result = set_token_manual(token)
            await update.message.reply_text(result)
        except ImportError:
            await update.message.reply_text(
                "⚠️ 领券模块未就绪，请检查 wechat_coupon 模块"
            )
        except Exception as e:
            logger.error("设置 token 异常: %s", e)
            await update.message.reply_text(f"❌ 设置出错: {e}")

    @requires_auth
    @with_typing
    async def cmd_intel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """处理 /intel 命令

        无参数时显示交互式按钮菜单；
        带参数时直接查询指定分类的情报。

        用法:
            /intel          — 显示分类菜单
            /intel 金融     — 查看金融经济情报
            /intel military — 查看军事安全情报
            /intel 搜索关键词 — 按关键词搜索
        """
        try:
            if not _WORLDMONITOR_AVAILABLE:
                await update.message.reply_text(
                    "⚠️ 情报系统暂时不可用，请联系管理员检查。"
                )
                return

            args = context.args

            # 无参数 → 显示交互式菜单
            if not args:
                await update.message.reply_text(
                    "🌍 <b>全球情报速递</b>\n\n"
                    "选择你感兴趣的领域，获取最新情报：",
                    parse_mode="HTML",
                    reply_markup=_build_intel_keyboard(),
                )
                return

            # 有参数 → 尝试匹配分类
            user_input = " ".join(args)
            cat_key = _category_name_to_key(user_input)

            if cat_key and _is_industry_key(cat_key):
                # 匹配到行业分类
                cat_info = INDUSTRY_CATEGORIES[cat_key]
                await update.message.reply_text(
                    f"⏳ 正在获取 {cat_info['emoji']} {cat_info['name']} 情报..."
                )
                items = await fetch_category_news(cat_key)
                if items:
                    header = f"{cat_info['emoji']} <b>{cat_info['name']}情报</b>\n\n"
                    body = format_intel_items(items, max_items=6)
                    await update.message.reply_text(
                        header + body,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                else:
                    await update.message.reply_text(
                        f"{cat_info['emoji']} {cat_info['name']}暂无最新情报。"
                    )
                return

            if cat_key and _is_region_key(cat_key):
                # 匹配到地区分类
                reg_info = REGION_CATEGORIES[cat_key]
                await update.message.reply_text(
                    f"⏳ 正在获取 {reg_info['emoji']} {reg_info['name']} 情报..."
                )
                items = await fetch_region_news(cat_key)
                if items:
                    header = f"{reg_info['emoji']} <b>{reg_info['name']}情报</b>\n\n"
                    body = format_intel_items(items, max_items=6)
                    await update.message.reply_text(
                        header + body,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                else:
                    await update.message.reply_text(
                        f"{reg_info['emoji']} {reg_info['name']}暂无最新情报。"
                    )
                return

            # 都没匹配到 → 作为自由搜索关键词
            await update.message.reply_text(f"⏳ 正在搜索「{user_input}」相关情报...")
            items = await fetch_news_by_query(user_input)
            if items:
                header = f"🔍 <b>「{_escape_html(user_input)}」搜索结果</b>\n\n"
                body = format_intel_items(items, max_items=6)
                await update.message.reply_text(
                    header + body,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            else:
                await update.message.reply_text(
                    f"🔍 未找到「{user_input}」相关情报，请换个关键词试试。"
                )
        except Exception as e:
            logger.warning("[cmd_intel] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    async def handle_intel_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """处理所有 intel_ 前缀的回调按钮

        回调数据格式:
          intel_cat:<category_key>  — 行业分类
          intel_reg:<region_key>    — 地区分类
          intel_brief               — 每日情报简报
        """
        query = update.callback_query
        await query.answer()

        if not _WORLDMONITOR_AVAILABLE:
            await query.edit_message_text("⚠️ 情报系统暂时不可用。")
            return

        data = query.data or ""

        if data.startswith("intel_cat:"):
            # 行业分类查询
            cat_key = data.split(":", 1)[1]
            cat_info = INDUSTRY_CATEGORIES.get(cat_key)
            if not cat_info:
                await query.edit_message_text("⚠️ 未知的行业分类。")
                return

            await query.edit_message_text(
                f"⏳ 正在获取 {cat_info['emoji']} {cat_info['name']} 情报..."
            )

            items = await fetch_category_news(cat_key)
            if items:
                header = f"{cat_info['emoji']} <b>{cat_info['name']}情报</b>\n\n"
                body = format_intel_items(items, max_items=6)
                await query.edit_message_text(
                    header + body,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            else:
                await query.edit_message_text(
                    f"{cat_info['emoji']} {cat_info['name']}暂无最新情报。",
                )

        elif data.startswith("intel_reg:"):
            # 地区分类查询
            reg_key = data.split(":", 1)[1]
            reg_info = REGION_CATEGORIES.get(reg_key)
            if not reg_info:
                await query.edit_message_text("⚠️ 未知的地区分类。")
                return

            await query.edit_message_text(
                f"⏳ 正在获取 {reg_info['emoji']} {reg_info['name']} 情报..."
            )

            items = await fetch_region_news(reg_key)
            if items:
                header = f"{reg_info['emoji']} <b>{reg_info['name']}情报</b>\n\n"
                body = format_intel_items(items, max_items=6)
                await query.edit_message_text(
                    header + body,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            else:
                await query.edit_message_text(
                    f"{reg_info['emoji']} {reg_info['name']}暂无最新情报。",
                )

        elif data == "intel_brief":
            # 每日综合情报简报
            await query.edit_message_text("⏳ 正在生成每日情报简报，请稍候...")

            brief = await generate_intel_brief()
            if brief:
                # 简报可能较长，使用 send_message 发新消息避免 edit 长度限制
                chat_id = query.message.chat_id
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=brief,
                        disable_web_page_preview=True,
                    )
                    await query.edit_message_text("✅ 每日情报简报已生成，请查看上方消息。")
                except Exception as e:
                    logger.error("发送情报简报失败: %s", e)
                    # 回退：尝试直接编辑消息
                    truncated = brief[:4000] + "\n\n(内容过长，已截断)" if len(brief) > 4000 else brief
                    await query.edit_message_text(truncated)
            else:
                await query.edit_message_text("⚠️ 情报简报生成失败，请稍后再试。")

        else:
            await query.edit_message_text("⚠️ 未知的操作。")


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
