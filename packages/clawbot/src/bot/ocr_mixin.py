# ocr_mixin.py — OCR 处理 Mixin (图片识别 / 文档解析)
# 从 message_mixin.py 拆分而来，处理图片和文档的 OCR 识别与场景路由

import io
import logging

from src.bot.globals import history_store, shared_memory, send_long_message
from src.ocr_service import ocr_image, OcrResult
from src.ocr_router import classify_ocr_scene, OcrScene
from src.ocr_processors import process_financial_scene, process_ecommerce_scene
from src.telegram_markdown import md_to_html
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


class OCRHandlerMixin:
    """图片/文档 OCR 识别 + 场景路由 Mixin

    提供:
      - handle_photo()        — 图片消息 → OCR → 场景路由（交易/电商/通用）
      - handle_document_ocr() — 文档消息 → Docling 结构化 / OCR 降级
    """

    # 用户明确要求 OCR 时的关键词列表
    _OCR_EXPLICIT_KEYWORDS = ("OCR", "ocr", "识别文字", "提取文字", "文字识别", "识别", "文字", "提取")

    async def handle_photo(self, update, context):
        '''处理图片消息 — 私聊默认 Vision / 群聊走 OCR+场景路由'''
        try:
            chat_id = update.effective_chat.id
            user = update.effective_user
            caption = update.message.caption or ""
            is_group = update.effective_chat.type in ("group", "supergroup")

            # 群聊门控：仅在被 @ 或 caption 含触发词时才处理
            if is_group:
                bot_username = (await context.bot.get_me()).username or ""
                mentioned = f"@{bot_username}" in (caption or "")
                trigger = any(w in caption for w in ("OCR", "ocr", "识别", "文字", "提取", "分析", "竞品", "财报"))
                if not mentioned and not trigger:
                    return

            # 下载图片（Vision 和 OCR 都需要）
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            image_bytes = buf.getvalue()

            logger.info(f"[Photo] 收到图片 from {user.id}, {len(image_bytes)} bytes, "
                         f"chat_type={'group' if is_group else 'private'}")

            # ── 私聊默认 Vision 分析 ──────────────────────────────
            # 除非用户明确说"OCR/识别文字"，否则直接用 Vision 模型理解图片
            # 这比 OCR→场景路由 更自然，用户可以直接追问图片内容
            ocr_requested = any(w in caption for w in self._OCR_EXPLICIT_KEYWORDS)
            if not is_group and not ocr_requested:
                hint_msg = await update.message.reply_text("🖼️ 正在分析图片...")
                try:
                    from src.tools.vision import analyze_image
                    vision_prompt = caption or "请仔细描述这张图片的内容，包括文字、图表、人物、场景等所有重要信息。"
                    vision_result = await analyze_image(bytes(image_bytes), vision_prompt)

                    # 删除处理中提示
                    try:
                        await hint_msg.delete()
                    except Exception as e:
                        logger.debug("删除处理提示消息失败(可忽略): %s", e)
                        # 发送分析结果
                        reply_text = f"🖼️ 图片分析:\n\n{vision_result}"
                        await send_long_message(
                            chat_id, reply_text, context,
                            reply_to_message_id=update.message.message_id,
                        )
                        # 注入对话历史 — 用户可以基于图片内容继续追问
                        try:
                            # 记录用户发图行为
                            user_ctx = "[用户发送了一张图片]"
                            if caption:
                                user_ctx += f" 附言: {caption}"
                            history_store.add_message(
                                getattr(self, 'bot_id', 'system'), chat_id,
                                "user", user_ctx)
                            # 记录 Vision 分析结果
                            history_store.add_message(
                                getattr(self, 'bot_id', 'system'), chat_id,
                                "assistant", f"[图片分析结果] {vision_result[:1500]}")
                        except Exception as e:
                            logger.warning(f"[Photo] Vision 上下文注入失败: {scrub_secrets(str(e))}")
                        return
                    # Vision 返回空 → 降级到 OCR 流程
                    logger.info("[Photo] Vision 返回空，降级到 OCR 流程")
                except Exception as ve:
                    logger.warning(f"[Photo] 私聊 Vision 分析失败，降级到 OCR: {ve}")
                    # 删除处理中提示（Vision 失败场景）
                    try:
                        await hint_msg.delete()
                    except Exception as e:
                        logger.debug("删除处理提示消息失败(可忽略): %s", e)

            # ── OCR 流程（群聊默认 / 私聊显式请求 / Vision 降级） ──
            hint_msg = await update.message.reply_text("🔍 正在识别图片文字...")

            # 调用 OCR
            result: OcrResult = await ocr_image(
                image_bytes,
                mime_type="image/jpeg",
                user_id=user.id,
                file_unique_id=photo.file_unique_id,
            )

            # 删除处理中提示
            try:
                await hint_msg.delete()
            except Exception as e:
                logger.debug("删除OCR处理提示消息失败(可忽略): %s", e)

            # OCR 失败
            if not result.ok:
                await send_long_message(chat_id, f"⚠️ OCR 失败: {result.error}", context,
                                        reply_to_message_id=update.message.message_id)
                return

            # OCR 无文字 → 降级到 Vision 模型分析
            if not result.text:
                try:
                    from src.tools.vision import analyze_image
                    vision_prompt = caption or "描述这张图片的内容"
                    vision_result = await analyze_image(bytes(image_bytes), vision_prompt)
                    if vision_result:
                        await send_long_message(
                            chat_id,
                            f"🖼️ 图片分析:\n\n{vision_result}",
                            context,
                            reply_to_message_id=update.message.message_id,
                        )
                        return
                except Exception as ve:
                    logger.debug(f"[OCR] Vision fallback 失败: {ve}")

                await send_long_message(chat_id, "📷 图片已收到，未识别到文字内容。", context,
                                        reply_to_message_id=update.message.message_id)
                return

            # 场景路由
            scene_match = classify_ocr_scene(result.text, caption)

            if scene_match.scene == OcrScene.FINANCIAL:
                # 交易/财报场景
                proc_result = await process_financial_scene(
                    result.text, caption, user.id, chat_id, shared_memory)

                tag = " (缓存)" if result.cached else ""
                reply_parts = [f"📄 OCR 识别结果{tag}:\n\n{result.text}"]
                reply_parts.append(f"\n{'─' * 20}")
                reply_parts.append(f"🎯 场景: 交易分析 ({scene_match.confidence:.0%})")
                if proc_result.success:
                    reply_parts.append(proc_result.summary)
                    if proc_result.next_step:
                        reply_parts.append(f"\n💡 {proc_result.next_step}")

                await send_long_message(chat_id, "\n".join(reply_parts), context,
                                        reply_to_message_id=update.message.message_id)

                # 注入对话上下文（可追问）
                if proc_result.context_injection:
                    try:
                        history_store.add_message(
                            getattr(self, 'bot_id', 'system'), chat_id,
                            "assistant", proc_result.context_injection)
                    except Exception as e:
                        logger.warning(f"[OCR] 交易场景上下文注入失败: {scrub_secrets(str(e))}")
                if proc_result.auto_invest_topic and not is_group:
                    try:
                        await send_long_message(chat_id,
                            f"🚀 自动触发投资分析: {proc_result.auto_invest_topic}\n"
                            "发送 /stop_discuss 可中断", context)
                        # 模拟 /invest 命令
                        context.args = proc_result.auto_invest_topic.split()
                        await self.cmd_invest(update, context)
                    except Exception as e:
                        logger.error(f"[OCR] 自动触发 /invest 失败: {scrub_secrets(str(e))}")

            elif scene_match.scene == OcrScene.ECOMMERCE:
                # 电商/竞品场景
                proc_result = await process_ecommerce_scene(
                    result.text, caption, user.id, chat_id, shared_memory)

                tag = " (缓存)" if result.cached else ""
                reply_parts = [f"📄 OCR 识别结果{tag}:\n\n{result.text}"]
                reply_parts.append(f"\n{'─' * 20}")
                reply_parts.append(f"🎯 场景: 竞品分析 ({scene_match.confidence:.0%})")
                if proc_result.success:
                    reply_parts.append(proc_result.summary)
                    if proc_result.next_step:
                        reply_parts.append(f"\n💡 定价建议: {proc_result.next_step}")

                await send_long_message(chat_id, "\n".join(reply_parts), context,
                                        reply_to_message_id=update.message.message_id)

                # 注入对话上下文（可追问）
                if proc_result.context_injection:
                    try:
                        history_store.add_message(
                            getattr(self, 'bot_id', 'system'), chat_id,
                            "assistant", proc_result.context_injection)
                    except Exception as e:
                        logger.warning(f"[OCR] 电商场景上下文注入失败: {scrub_secrets(str(e))}")

            else:
                # 通用场景: OCR 文字 + Vision 补充分析
                tag = " (缓存)" if result.cached else ""
                reply = f"📄 OCR 识别结果{tag}:\n\n{result.text}"
                if caption:
                    reply += f"\n\n💬 附言: {caption}"

                # Vision 补充: 用户有 caption 指令时，用 Vision 模型做进一步分析
                if caption and any(w in caption for w in ("分析", "解释", "翻译", "总结", "看看", "什么意思")):
                    try:
                        from src.tools.vision import analyze_image
                        vision_result = await analyze_image(
                            bytes(image_bytes),
                            f"图片中的文字内容如下:\n{result.text[:500]}\n\n用户要求: {caption}",
                        )
                        if vision_result:
                            reply += f"\n\n{'─' * 20}\n🖼️ 图片分析:\n{vision_result}"
                    except Exception as ve:
                        logger.debug(f"[OCR] Vision 补充分析失败: {ve}")

                await send_long_message(chat_id, reply, context,
                                        reply_to_message_id=update.message.message_id)

        except Exception as e:
            logger.error(f"[OCR] handle_photo 异常: {scrub_secrets(str(e))}", exc_info=True)
            try:
                await send_long_message(
                    update.effective_chat.id, f"⚠️ 图片处理异常: {e}", context,
                    reply_to_message_id=update.message.message_id)
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)


    async def handle_document_ocr(self, update, context):
        '''处理文档消息（PDF/DOCX/PPTX/XLSX/图片）— Docling 结构化理解 + OCR 降级'''
        try:
            chat_id = update.effective_chat.id
            user = update.effective_user
            doc = update.message.document
            mime = doc.mime_type or ""
            fname = doc.file_name or "document"
            caption = update.message.caption or ""
            is_group = update.effective_chat.type in ("group", "supergroup")

            # 仅处理图片、PDF 和 Office 文档
            supported_mimes = (
                "image/", "application/pdf",
                "application/vnd.openxmlformats-officedocument",  # docx/pptx/xlsx
                "application/msword",  # .doc
                "application/vnd.ms-excel",  # .xls
                "application/vnd.ms-powerpoint",  # .ppt
            )
            if not any(mime.startswith(m) for m in supported_mimes):
                return

            # 群聊门控
            if is_group:
                bot_username = (await context.bot.get_me()).username or ""
                mentioned = f"@{bot_username}" in (caption or "")
                trigger = any(w in caption for w in ("OCR", "ocr", "识别", "文字", "提取", "分析", "总结", "摘要"))
                if not mentioned and not trigger:
                    return

            # 处理中提示
            hint_msg = await update.message.reply_text(f"🔍 正在分析 {fname}...")

            logger.info(f"[DOC] 收到文档 {fname} ({mime}, {doc.file_size} bytes) from {user.id}")

            file = await context.bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            file_bytes = buf.getvalue()

            # ── Docling 结构化理解 (优先) ──────────────────────────
            docling_supported = ('.pdf', '.docx', '.pptx', '.xlsx', '.doc')
            docling_handled = False

            if fname.lower().endswith(docling_supported):
                try:
                    from src.tools.docling_service import (
                        summarize_document, HAS_DOCLING,
                    )
                    if HAS_DOCLING:
                        # 写入临时文件 — Docling 需要文件路径
                        import os
                        import tempfile
                        suffix = os.path.splitext(fname)[1] or ".pdf"
                        with tempfile.NamedTemporaryFile(
                            suffix=suffix, delete=False,
                        ) as tmp:
                            tmp.write(file_bytes)
                            local_path = tmp.name

                        try:
                            if caption:
                                # 用户附带了问题 → 摘要+问答模式
                                result_text = await summarize_document(
                                    local_path, question=caption,
                                )
                            else:
                                # 无问题 → 自动摘要
                                result_text = await summarize_document(local_path)

                            if result_text:
                                # 删除处理中提示
                                try:
                                    await hint_msg.delete()
                                except Exception:
                                    logger.debug("Silenced exception", exc_info=True)
                                try:
                                    safe = md_to_html(result_text)
                                    await update.message.reply_text(
                                        safe, parse_mode="HTML",
                                        reply_to_message_id=update.message.message_id,
                                    )
                                except Exception as e:  # noqa: F841
                                    # HTML 渲染失败 → 纯文本降级
                                    await send_long_message(
                                        chat_id, result_text, context,
                                        reply_to_message_id=update.message.message_id,
                                    )
                                docling_handled = True
                        finally:
                            # 清理临时文件
                            try:
                                os.unlink(local_path)
                            except Exception:
                                logger.debug("Silenced exception", exc_info=True)
                except Exception as e:
                    logger.debug(f"[DOC] Docling 处理失败，降级到 OCR: {e}")

            if docling_handled:
                return

            # ── OCR 降级 (图片 + Docling 失败时) ──────────────────
            result: OcrResult = await ocr_image(
                file_bytes,
                mime_type=mime,
                user_id=user.id,
                file_unique_id=doc.file_unique_id,
            )

            # 删除处理中提示
            try:
                await hint_msg.delete()
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

            if result.ok and result.text:
                tag = " (缓存)" if result.cached else ""
                reply = f"📄 {fname} 识别结果{tag}:\n\n{result.text}"
                if caption:
                    reply += f"\n\n💬 附言: {caption}"
                await send_long_message(chat_id, reply, context,
                                        reply_to_message_id=update.message.message_id)
            elif result.ok and not result.text:
                await send_long_message(chat_id, f"📎 {fname} 已收到，未识别到文字内容。", context,
                                        reply_to_message_id=update.message.message_id)
            else:
                await send_long_message(chat_id, f"⚠️ {fname} OCR 失败: {result.error}", context,
                                        reply_to_message_id=update.message.message_id)
        except Exception as e:
            logger.error(f"[DOC] handle_document_ocr 异常: {scrub_secrets(str(e))}", exc_info=True)
            try:
                await send_long_message(
                    update.effective_chat.id, f"⚠️ 文档处理异常: {e}", context,
                    reply_to_message_id=update.message.message_id)
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
