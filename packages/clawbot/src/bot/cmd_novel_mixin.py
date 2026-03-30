"""
Bot — AI 小说工坊 命令 Mixin

包含功能:
  - AI 小说创作 (新建 / 续写 / 查看 / 导出 / TTS)
"""

import logging
from pathlib import Path

from src.constants import TG_SAFE_LENGTH
from src.bot.auth import requires_auth

logger = logging.getLogger(__name__)


class NovelCommandsMixin:
    @requires_auth
    async def cmd_novel(self, update, context):
        """AI小说写作 — /novel <子命令>"""
        from src.novel_writer import get_novel_writer
        
        writer = get_novel_writer()
        args = context.args or []
        sub = args[0] if args else "help"
        user_id = update.effective_user.id if update.effective_user else 0
        
        if sub == "help" or sub == "帮助":
            help_text = (
                "📖 AI 小说工坊\n\n"
                "子命令:\n"
                "  /novel new <题材> [风格] — 创建新小说\n"
                "  /novel continue <ID> — 续写下一章\n"
                "  /novel status <ID> — 查看进度\n"
                "  /novel list — 我的小说列表\n"
                "  /novel export <ID> — 导出 TXT\n"
                "  /novel tts <ID> <章节号> — 章节转语音\n\n"
                "示例:\n"
                "  /novel new 都市修仙 轻松搞笑\n"
                "  /novel new 末日生存\n"
                "  /novel continue 1"
            )
            await update.message.reply_text(help_text)
            return
        
        if sub == "new" or sub == "新建":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定题材: /novel new <题材> [风格]\n例: /novel new 都市修仙 轻松搞笑")
                return
            genre = args[1]
            style = " ".join(args[2:]) if len(args) > 2 else "轻松有趣"
            await update.message.reply_text(f"📖 正在构思《{genre}》小说，生成大纲中...")
            result = await writer.create_novel(genre, style, user_id)
            if "error" in result:
                await update.message.reply_text(f"⚠️ 创建失败: {result['error']}")
                return
            outline = result.get("outline", {})
            msg = (
                f"📖 新小说创建成功!\n\n"
                f"📕 《{result['title']}》\n"
                f"📝 {result.get('tagline', '')}\n"
                f"🆔 小说ID: {result['novel_id']}\n\n"
            )
            # 显示角色
            chars = outline.get("characters", [])
            if chars:
                msg += "👥 主要角色:\n"
                for c in chars[:5]:
                    msg += f"  • {c.get('name','')} ({c.get('role','')}): {c.get('personality','')}\n"
            # 显示章节数
            total_chapters = sum(len(act.get("chapters", [])) for act in outline.get("acts", []))
            if total_chapters:
                msg += f"\n📋 大纲: {len(outline.get('acts', []))}幕 {total_chapters}章\n"
            msg += f"\n发送 /novel continue {result['novel_id']} 开始写第一章"
            await update.message.reply_text(msg)
            return
        
        if sub == "continue" or sub == "续写":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定小说ID: /novel continue <ID>")
                return
            try:
                novel_id = int(args[1])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❓ 小说ID必须是数字")
                return
            await update.message.reply_text("✍️ 正在续写中，请稍候（约30秒）...")
            result = await writer.write_next_chapter(novel_id)
            if "error" in result:
                await update.message.reply_text(f"⚠️ 续写失败: {result['error']}")
                return
            # Telegram 消息长度限制 (TG_SAFE_LENGTH from constants)
            content = result["content"]
            header = f"📖 《续写》第{result['chapter_num']}章 {result['title']}\n字数: {result['word_count']}\n\n"
            if len(header + content) > TG_SAFE_LENGTH:
                content = content[:3900] + "\n\n...(完整内容请导出 TXT)"
            await update.message.reply_text(header + content)
            return
        
        if sub == "status" or sub == "进度":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定小说ID: /novel status <ID>")
                return
            try:
                novel_id = int(args[1])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❓ 小说ID必须是数字")
                return
            status = writer.get_novel_status(novel_id)
            if "error" in status:
                await update.message.reply_text(f"⚠️ {status['error']}")
                return
            msg = (
                f"📖 《{status['title']}》\n"
                f"📝 {status.get('tagline', '')}\n"
                f"🎭 {status['genre']} · {status['style']}\n"
                f"📊 {status['chapters']}章 / {status['total_words']}字\n\n"
            )
            if status["chapter_list"]:
                msg += "章节列表:\n"
                for ch in status["chapter_list"]:
                    msg += f"  第{ch['num']}章 {ch['title']} ({ch['words']}字)\n"
            await update.message.reply_text(msg)
            return
        
        if sub == "list" or sub == "列表":
            novels = writer.list_novels(user_id)
            if not novels:
                await update.message.reply_text("📖 还没有创建过小说\n发送 /novel new <题材> 开始创作")
                return
            msg = "📚 我的小说:\n\n"
            for n in novels:
                msg += f"  #{n['id']} 《{n['title']}》 {n['genre']} — {n['chapters']}章/{n['words']}字\n"
            await update.message.reply_text(msg)
            return
        
        if sub == "export" or sub == "导出":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定小说ID: /novel export <ID>")
                return
            try:
                novel_id = int(args[1])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❓ 小说ID必须是数字")
                return
            path = writer.export_txt(novel_id)
            if not path:
                await update.message.reply_text("⚠️ 导出失败（小说不存在或无章节）")
                return
            try:
                with open(path, "rb") as f:
                    await update.message.reply_document(document=f, filename=Path(path).name)
            except Exception as e:
                await update.message.reply_text(f"⚠️ 文件发送失败: {e}")
            return
        
        if sub == "tts":
            if len(args) < 3:
                await update.message.reply_text("❓ 用法: /novel tts <小说ID> <章节号>")
                return
            try:
                novel_id = int(args[1])
                chapter_num = int(args[2])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❓ ID和章节号必须是数字")
                return
            # 获取章节内容
            status = writer.get_novel_status(novel_id)
            if "error" in status:
                await update.message.reply_text(f"⚠️ {status['error']}")
                return
            # 读取章节
            with writer._conn() as conn:
                ch = conn.execute(
                    "SELECT content FROM chapters WHERE novel_id=? AND chapter_num=?",
                    (novel_id, chapter_num)
                ).fetchone()
            if not ch:
                await update.message.reply_text(f"⚠️ 第{chapter_num}章不存在")
                return
            await update.message.reply_text(f"🎤 正在将第{chapter_num}章转为语音...")
            from src.tools.tts_tool import text_to_speech
            audio = await text_to_speech(ch["content"][:5000])
            if audio:
                try:
                    with open(audio, "rb") as f:
                        await update.message.reply_voice(voice=f)
                    Path(audio).unlink(missing_ok=True)
                except Exception as e:
                    logger.error("音频发送失败: %s", e)
                    await update.message.reply_text("⚠️ 音频发送失败")
            else:
                await update.message.reply_text("⚠️ 语音生成失败")
            return
        
        await update.message.reply_text(f"❓ 未知子命令: {sub}\n发送 /novel help 查看帮助")

    # ---- 降价监控管理 ----

