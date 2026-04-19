# voice_handler.py — 语音消息处理：STT 三级降级链 (Groq → OpenAI → Deepgram)
# 从 message_mixin.py 拆分而来

import io
import logging

from src.http_client import ResilientHTTPClient

logger = logging.getLogger(__name__)

# 模块级别 HTTP 客户端（语音转写）
_http_voice = ResilientHTTPClient(timeout=30.0, name="voice_stt")


class VoiceHandlerMixin:
    """语音消息处理 Mixin — 提供 handle_voice() 方法。

    依赖宿主类提供: _is_authorized(), handle_message(), bot_id
    """

    async def handle_voice(self, update, context):
        """处理语音消息 — 完整语音交互闭环

        STT 降级链: Groq Whisper (免费) → OpenAI Whisper (付费) → Deepgram Nova-3 → 失败提示
        流程: 下载语音 → STT 转文字 → LLM 处理 → TTS 回语音

        语音输入时自动以语音回复（无需手动开启 /voice），实现真正的对话闭环。
        """
        if not self._is_authorized(update.effective_user.id):
            return

        chat_id = update.effective_chat.id
        voice = update.message.voice or update.message.audio
        if not voice:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # 下载语音文件
            file = await context.bot.get_file(voice.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            buf.seek(0)
            buf.name = "voice.ogg"

            import os

            transcribed = None

            # ── 第一优先: Groq 免费 Whisper ──────────────────────
            # Groq 提供免费的 whisper-large-v3-turbo，与 OpenAI Whisper 请求格式完全相同
            # 限制: 20 RPM (每分钟 20 次请求)
            groq_key = os.environ.get("GROQ_API_KEY", "")
            if groq_key and not transcribed:
                try:
                    # 每次请求需要独立的 BytesIO 游标位置
                    buf.seek(0)
                    resp = await _http_voice.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        files={"file": ("voice.ogg", buf, "audio/ogg")},
                        data={
                            "model": "whisper-large-v3-turbo",
                            "language": "zh",  # 优先中文识别
                        },
                    )
                    if resp.status_code == 200:
                        transcribed = resp.json().get("text", "")
                        if transcribed:
                            logger.info("[Voice] Groq Whisper 转写成功 (%d 字符)", len(transcribed))
                    elif resp.status_code == 429:
                        # Groq 免费版 20 RPM 限速，降级到 OpenAI
                        logger.info("[Voice] Groq Whisper 触发限速 (429)，降级到 OpenAI")
                    else:
                        logger.debug("[Voice] Groq Whisper 返回 %d: %s", resp.status_code, resp.text[:200])
                except Exception as groq_err:
                    logger.debug("[Voice] Groq Whisper 失败，降级到 OpenAI: %s", groq_err)

            # ── 第二优先: OpenAI Whisper (付费) ──────────────────
            if not transcribed:
                openai_key = os.environ.get("OPENAI_API_KEY", "")
                if openai_key:
                    try:
                        buf.seek(0)
                        resp = await _http_voice.post(
                            "https://api.openai.com/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {openai_key}"},
                            files={"file": ("voice.ogg", buf, "audio/ogg")},
                            data={"model": "whisper-1"},
                        )
                        if resp.status_code == 200:
                            transcribed = resp.json().get("text", "")
                            if transcribed:
                                logger.info("[Voice] OpenAI Whisper 转写成功 (%d 字符)", len(transcribed))
                    except Exception as whisper_err:
                        logger.debug("[Voice] OpenAI Whisper 失败: %s", whisper_err)

            # ── 第三优先: Deepgram Nova-3 (付费) ─────────────────
            # 搬运 deepgram_stt.py 的能力，作为 Whisper 全部失败时的降级
            if not transcribed:
                try:
                    from src.tools.deepgram_stt import transcribe_audio

                    buf.seek(0)
                    audio_data = buf.read()
                    deepgram_result = await transcribe_audio(audio_data, language="zh")
                    if deepgram_result:
                        transcribed = deepgram_result
                        logger.info("[Voice] Deepgram Nova-3 转写成功 (%d 字符)", len(transcribed))
                except Exception as dg_err:
                    logger.debug("[Voice] Deepgram 转写失败: %s", dg_err)

            # ── 全部失败 ─────────────────────────────────────────
            if not transcribed:
                await update.message.reply_text(
                    "抱歉，没听清你说什么，请再说一次或者发文字消息吧。",
                    reply_to_message_id=update.message.message_id,
                )
                return

            # 显示识别结果
            await update.message.reply_text(
                f"🎤 识别: {transcribed[:200]}",
                reply_to_message_id=update.message.message_id,
            )

            # 标记本次为语音输入 — handle_message 结束后会自动以语音回复
            context.user_data["_voice_input"] = True

            # 伪造文本消息，复用 handle_message 流程
            update.message.text = transcribed
            await self.handle_message(update, context)

        except Exception as e:
            logger.error("[Voice] 语音处理失败: %s", e)
            await update.message.reply_text("抱歉，语音处理出了点问题，请发文字消息吧。")
        finally:
            # 清理语音输入标记，防止后续文本消息被误判
            context.user_data.pop("_voice_input", None)
