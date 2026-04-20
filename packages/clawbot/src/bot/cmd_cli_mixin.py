"""CLI-Anything Telegram 命令 — /cli 系列

让用户通过 Telegram 控制桌面软件:
- /cli list          — 列出可用工具
- /cli run gimp project new --width 1920 --height 1080
- /cli install blender
- /cli help <tool>   — 显示工具帮助

搬运 HKUDS/CLI-Anything (31K★) — 把任何桌面 GUI 变成命令行。
"""

import logging

from src.bot.auth import requires_auth
from src.telegram_ux import with_typing
from src.integrations.cli_anything_bridge import CLIAnythingManager

logger = logging.getLogger(__name__)


class CLICommandsMixin:
    """CLI-Anything 命令 Mixin — 提供 /cli 系列命令"""

    @requires_auth
    @with_typing
    async def cmd_cli(self, update, context):
        """统一入口: /cli <子命令> [参数...]

        子命令:
            list                — 列出已安装的 CLI 工具
            run <tool> [args]   — 执行工具命令
            install <tool>      — 安装新工具
            help <tool>         — 查看工具帮助
            status              — 查看 CLI-Anything 状态
        """
        try:
            args = context.args or []

            # 没有参数时显示帮助
            if not args:
                await update.message.reply_text(self._cli_help_text())
                return

            sub_cmd = args[0].lower().strip()
            rest = args[1:]

            if sub_cmd in {"list", "ls", "工具"}:
                await self._cli_list(update, context)

            elif sub_cmd in {"run", "exec", "执行"}:
                if not rest:
                    await update.message.reply_text(
                        "❌ 用法: /cli run <工具名> [参数...]\n"
                        "例如: /cli run gimp project new"
                    )
                    return
                tool_name = rest[0]
                tool_args = rest[1:]
                await self._cli_run(update, context, tool_name, tool_args)

            elif sub_cmd in {"install", "安装"}:
                if not rest:
                    await update.message.reply_text(
                        "❌ 用法: /cli install <工具名>\n"
                        "例如: /cli install blender"
                    )
                    return
                await self._cli_install(update, context, rest[0])

            elif sub_cmd in {"help", "帮助"}:
                if not rest:
                    await update.message.reply_text(self._cli_help_text())
                    return
                await self._cli_tool_help(update, context, rest[0])

            elif sub_cmd in {"status", "状态"}:
                await self._cli_status(update, context)

            else:
                await update.message.reply_text(
                    f"❓ 不认识的子命令: {sub_cmd}\n\n"
                    + self._cli_help_text()
                )

        except Exception:
            logger.exception("[cmd_cli] 执行异常")
            await update.message.reply_text(
                "❌ CLI 命令执行出错，请稍后再试"
            )

    async def _cli_list(self, update, context):
        """列出已安装的 CLI-Anything 工具"""
        mgr = CLIAnythingManager.get_instance()
        tools = mgr.discover()

        if not tools:
            await update.message.reply_text(
                "📭 还没有安装任何 CLI-Anything 工具\n\n"
                "可以用 /cli install <工具名> 安装\n"
                "例如: /cli install gimp"
            )
            return

        lines = ["<b>🔧 已安装的 CLI 工具</b>\n"]
        for i, tool in enumerate(tools, 1):
            lines.append(
                f"  {i}. <code>{tool['name']}</code> — {tool['description']}"
            )
        lines.append(f"\n共 {len(tools)} 个工具")
        lines.append("用法: /cli run <工具名> [参数...]")

        await update.message.reply_text(
            "\n".join(lines), parse_mode="HTML"
        )

    async def _cli_run(self, update, context, tool_name: str, args: list):
        """执行 CLI 工具命令"""
        mgr = CLIAnythingManager.get_instance()

        # 发送执行中提示
        status_msg = await update.message.reply_text(
            f"⏳ 正在执行 <code>{tool_name}</code> ...",
            parse_mode="HTML",
        )

        result = await mgr.run(tool_name, args)

        if result["success"]:
            # 截断过长的输出
            output = result["output"]
            if len(output) > 3000:
                output = output[:3000] + "\n... (输出已截断)"

            await status_msg.edit_text(
                f"✅ <code>{tool_name}</code> 执行成功\n"
                f"⏱ 耗时: {result['duration_ms']}ms\n\n"
                f"<pre>{output}</pre>",
                parse_mode="HTML",
            )
        else:
            await status_msg.edit_text(
                f"❌ <code>{tool_name}</code> 执行失败\n"
                f"退出码: {result['exit_code']}\n\n"
                f"{result['output']}",
                parse_mode="HTML",
            )

    async def _cli_install(self, update, context, tool_name: str):
        """安装 CLI-Anything 工具"""
        status_msg = await update.message.reply_text(
            f"📦 正在安装 cli-anything-{tool_name} ...\n"
            "这可能需要一点时间"
        )

        mgr = CLIAnythingManager.get_instance()
        result = await mgr.install(tool_name)

        await status_msg.edit_text(result["message"])

    async def _cli_tool_help(self, update, context, tool_name: str):
        """显示某个工具的帮助信息"""
        mgr = CLIAnythingManager.get_instance()

        # 用 --help 参数执行工具获取帮助
        result = await mgr.run(tool_name, ["--help"])

        if result["output"]:
            output = result["output"]
            if len(output) > 3000:
                output = output[:3000] + "\n... (帮助信息已截断)"
            await update.message.reply_text(
                f"<b>📖 {tool_name} 帮助</b>\n\n"
                f"<pre>{output}</pre>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"❌ 无法获取 {tool_name} 的帮助信息\n"
                f"{result.get('output', '工具可能未安装')}"
            )

    async def _cli_status(self, update, context):
        """显示 CLI-Anything 状态"""
        mgr = CLIAnythingManager.get_instance()
        status = mgr.get_status()

        if status["available"]:
            tool_list = ""
            if status["tools"]:
                tool_list = "\n".join(
                    f"  • {t['name']}" for t in status["tools"]
                )
            await update.message.reply_text(
                f"<b>🔧 CLI-Anything 状态</b>\n\n"
                f"主程序: {'✅ 已安装' if status['cli_anything_installed'] else '⚠️ 未安装'}\n"
                f"工具数量: {status['tool_count']}\n"
                + (f"\n已安装工具:\n{tool_list}" if tool_list else ""),
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                "⚠️ CLI-Anything 未安装\n\n"
                "CLI-Anything 可以把桌面软件（如 GIMP、Blender）变成命令行工具，\n"
                "然后你就能在 Telegram 里远程控制它们。\n\n"
                "安装: pip install cli-anything"
            )

    @staticmethod
    def _cli_help_text() -> str:
        """返回 /cli 命令的帮助文本"""
        return (
            "<b>🔧 CLI-Anything — 桌面软件遥控器</b>\n\n"
            "让你在 Telegram 里控制电脑上的软件（GIMP、Blender 等）\n\n"
            "<b>命令:</b>\n"
            "  /cli list          — 列出已安装的工具\n"
            "  /cli run <工具> [参数]  — 执行命令\n"
            "  /cli install <工具>    — 安装新工具\n"
            "  /cli help <工具>       — 查看工具帮助\n"
            "  /cli status            — 查看状态\n\n"
            "<b>示例:</b>\n"
            "  /cli run gimp project new --width 1920\n"
            "  /cli install blender\n"
        )
