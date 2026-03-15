"""
ClawBot - 上下文管理模块 v2.0
- 本地压缩模式（零 API 调用）：截断+提取关键信息，不消耗请求次数
- AI 压缩模式（可选）：调用 LLM 生成高质量摘要
- 渐进式压缩：越旧的消息压缩比越高
- 支持关键信息标记保留
- 支持 SQLite HistoryStore 集成
"""
import json
from typing import List, Dict, Any, Optional, Callable, Tuple
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ContextManager:
    """上下文管理器 - 渐进式压缩和关键信息保留"""

    # Claude Opus 4.6 上下文窗口 200K，但实际安全线设低一些
    MAX_CONTEXT_TOKENS = 180000
    # 自动压缩触发阈值（token 数）
    COMPRESS_THRESHOLD = 60000
    # 强制压缩阈值（超过此值必须压缩，防止 API 超时）
    FORCE_COMPRESS_THRESHOLD = 100000
    # 压缩后保留的最近消息数
    KEEP_RECENT_MESSAGES = 10
    # 压缩后保留的最近消息 token 上限
    KEEP_RECENT_TOKENS = 20000

    # 关键信息标记关键词
    KEY_MARKERS = ["记住", "注意", "重要", "设置为", "偏好", "密码", "地址",
                   "名字叫", "我是", "请记住", "别忘了", "关键", "remember",
                   "important", "password", "config", "设定"]

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            import os
            env_dir = os.getenv('DATA_DIR')
            if env_dir:
                self.storage_dir = Path(env_dir)
            else:
                self.storage_dir = Path(__file__).parent.parent / "data"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.compressed_summary: Optional[str] = None
        self.key_facts: List[str] = []
        self.user_preferences: Dict[str, Any] = {}
        # 每个 (bot_id, chat_id) 的压缩状态
        self._compression_state: Dict[str, dict] = {}

    def estimate_tokens(self, messages: List[Dict]) -> int:
        """估算 token 数（CJK 感知）"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._count_text_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        total += self._count_text_tokens(block.get("text", ""))
                    elif block.get("type") in ("tool_result", "image"):
                        total += len(str(block.get("content", ""))) // 4
            # 每条消息的 role/结构开销约 4 tokens
            total += 4
        return total

    def estimate_single_message_tokens(self, msg: Dict) -> int:
        """估算单条消息的 token 数"""
        return self.estimate_tokens([msg])

    @staticmethod
    def _count_text_tokens(text: str) -> int:
        if not text:
            return 0
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        return chinese * 2 + (len(text) - chinese) // 4

    def should_compress(self, messages: List[Dict]) -> bool:
        """判断是否需要压缩"""
        return self.estimate_tokens(messages) > self.COMPRESS_THRESHOLD

    def must_compress(self, messages: List[Dict]) -> bool:
        """判断是否必须强制压缩（防止 API 超时）"""
        return self.estimate_tokens(messages) > self.FORCE_COMPRESS_THRESHOLD

    def _is_key_message(self, msg: Dict) -> bool:
        """判断消息是否包含关键信息"""
        content = msg.get("content", "")
        if isinstance(content, str):
            return any(kw in content for kw in self.KEY_MARKERS)
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    if any(kw in block.get("text", "") for kw in self.KEY_MARKERS):
                        return True
        return False

    def _get_message_text(self, msg: Dict, max_len: int = 300) -> str:
        """提取消息文本"""
        content = msg.get("content", "")
        if isinstance(content, str):
            return content[:max_len]
        if isinstance(content, list):
            parts = []
            for block in content:
                if block.get("type") == "text":
                    parts.append(block.get("text", "")[:max_len])
            return "\n".join(parts)[:max_len]
        return ""

    def _truncate_message(self, msg: Dict, max_chars: int = 200) -> Dict:
        """截断单条消息内容，保留结构"""
        content = msg.get("content", "")
        if isinstance(content, str):
            if len(content) <= max_chars:
                return msg
            truncated = content[:max_chars] + "...[已截断]"
            return {**msg, "content": truncated}
        if isinstance(content, list):
            new_blocks = []
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if len(text) > max_chars:
                        new_blocks.append({**block, "text": text[:max_chars] + "...[已截断]"})
                    else:
                        new_blocks.append(block)
                # 跳过图片等大块内容
            return {**msg, "content": new_blocks if new_blocks else "[多媒体内容已省略]"}
        return msg

    # ============ 核心：本地压缩（零 API 调用）============

    def compress_local(
        self,
        messages: List[Dict],
        target_tokens: Optional[int] = None,
    ) -> Tuple[List[Dict], str]:
        """
        本地压缩上下文 - 不消耗任何 API 请求。

        策略：
        1. 保留最近 N 条消息完整内容
        2. 提取关键消息（含关键词的）完整保留
        3. 中期消息截断为摘要
        4. 远期消息仅保留一行概要
        5. 生成本地摘要注入上下文头部

        Returns:
            (compressed_messages, summary_text)
        """
        if target_tokens is None:
            target_tokens = self.COMPRESS_THRESHOLD

        tokens = self.estimate_tokens(messages)
        if tokens <= target_tokens:
            return messages, ""

        total = len(messages)

        # 确定保留多少条最近消息（基于 token 预算）
        recent_budget = min(self.KEEP_RECENT_TOKENS, target_tokens // 3)
        recent_count = 0
        recent_tokens = 0
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = self.estimate_single_message_tokens(messages[i])
            if recent_tokens + msg_tokens > recent_budget and recent_count >= 4:
                break
            recent_tokens += msg_tokens
            recent_count += 1

        recent_count = max(recent_count, 4)  # 至少保留4条
        recent = messages[-recent_count:]
        older = messages[:-recent_count]

        if not older:
            return messages, ""

        # 分离关键消息和普通消息
        key_messages = []
        normal_messages = []
        for msg in older:
            if self._is_key_message(msg):
                key_messages.append(msg)
            else:
                normal_messages.append(msg)

        # 构建本地摘要
        summary_lines = []
        summary_lines.append(f"[对话摘要 - 已压缩 {len(older)} 条历史消息]")
        summary_lines.append("")

        # 提取对话主题
        topics = set()
        for msg in normal_messages:
            text = self._get_message_text(msg, max_len=100)
            if msg["role"] == "user" and len(text) > 5:
                # 取第一句作为主题
                first_line = text.split('\n')[0][:60]
                if first_line:
                    topics.add(first_line)

        if topics:
            summary_lines.append("讨论过的话题:")
            for t in list(topics)[-8:]:  # 最多8个话题
                summary_lines.append(f"  - {t}")
            summary_lines.append("")

        # 关键信息
        if key_messages:
            summary_lines.append("关键信息:")
            for msg in key_messages[-5:]:
                role = "用户" if msg["role"] == "user" else "助手"
                text = self._get_message_text(msg, max_len=150)
                summary_lines.append(f"  [{role}] {text}")
            summary_lines.append("")

        # 最近的普通消息概要（中期消息）
        mid_messages = normal_messages[-10:]
        if mid_messages:
            summary_lines.append("近期对话概要:")
            for msg in mid_messages:
                role = "用户" if msg["role"] == "user" else "助手"
                text = self._get_message_text(msg, max_len=80)
                if text.strip() and len(text) > 5:
                    summary_lines.append(f"  {role}: {text}")

        summary_text = "\n".join(summary_lines)

        # 重建消息列表
        new_messages = []

        # 1. 摘要作为上下文开头
        new_messages.append({
            "role": "user",
            "content": summary_text
        })
        new_messages.append({
            "role": "assistant",
            "content": "好的，我已了解之前的对话内容，请继续。"
        })

        # 2. 关键消息保留（截断长内容，最多5条）
        for msg in key_messages[-5:]:
            new_messages.append(self._truncate_message(msg, max_chars=300))

        # 3. 最近消息完整保留
        new_messages.extend(recent)

        # 检查压缩后是否在预算内，如果还超，进一步截断
        compressed_tokens = self.estimate_tokens(new_messages)
        if compressed_tokens > target_tokens:
            # 进一步截断：减少关键消息和摘要长度
            new_messages = self._aggressive_compress(new_messages, target_tokens)
            compressed_tokens = self.estimate_tokens(new_messages)

        logger.info(
            f"本地压缩: {tokens} -> {compressed_tokens} tokens "
            f"({total} -> {len(new_messages)} 条消息)"
        )

        self.compressed_summary = summary_text
        self._save_summary(summary_text, older)

        return new_messages, summary_text

    def _aggressive_compress(self, messages: List[Dict], target_tokens: int) -> List[Dict]:
        """激进压缩 - 当普通压缩后仍超标时使用"""
        # 从前往后截断，保留最后的消息
        result = []
        # 先加入最后 N 条
        keep_count = 6
        tail = messages[-keep_count:]
        head = messages[:-keep_count]

        # 头部只保留摘要（前2条）
        if len(head) >= 2:
            result.append(self._truncate_message(head[0], max_chars=500))
            result.append(head[1])  # assistant 确认
        result.extend(tail)

        return result

    # ============ AI 压缩（消耗1次 API 请求）============

    async def compress_with_ai(
        self,
        messages: List[Dict],
        ai_chat_func: Callable,
    ) -> Tuple[List[Dict], str]:
        """
        AI 辅助压缩 - 消耗1次 API 请求生成高质量摘要。
        仅在用户主动触发 /compact 时使用。

        Falls back to local compression on failure.
        """
        if not self.should_compress(messages):
            return messages, ""

        total = len(messages)
        recent = messages[-self.KEEP_RECENT_MESSAGES:]
        older = messages[:-self.KEEP_RECENT_MESSAGES]

        if not older:
            return messages, ""

        # 分离关键消息
        key_messages = []
        normal_messages = []
        for msg in older:
            if self._is_key_message(msg):
                key_messages.append(msg)
            else:
                normal_messages.append(msg)

        # 构建摘要 prompt
        summary_prompt = self._build_progressive_summary_prompt(
            normal_messages, key_messages
        )

        try:
            summary = await ai_chat_func(
                summary_prompt,
                system_override=(
                    "你是对话摘要助手。请按以下格式输出：\n"
                    "【关键决定】列出用户做出的重要决定\n"
                    "【已完成】列出已完成的任务\n"
                    "【待办】列出未完成的事项\n"
                    "【用户信息】列出用户透露的个人信息/偏好\n"
                    "【对话要点】简要概括对话主题和结论\n"
                    "保持简洁，每项不超过一行。"
                )
            )
        except Exception as e:
            logger.warning(f"AI 摘要失败，回退到本地压缩: {e}")
            return self.compress_local(messages)

        self.compressed_summary = summary
        self._save_summary(summary, older)

        # 重建消息列表
        new_messages = []
        new_messages.append({
            "role": "user",
            "content": f"[之前对话摘要 - {total - self.KEEP_RECENT_MESSAGES} 条消息]\n\n{summary}"
        })
        new_messages.append({
            "role": "assistant",
            "content": "好的，我已了解之前的对话内容。请继续。"
        })

        if key_messages:
            for msg in key_messages[-10:]:
                new_messages.append(msg)

        new_messages.extend(recent)

        compressed_tokens = self.estimate_tokens(new_messages)
        original_tokens = self.estimate_tokens(messages)
        logger.info(
            f"AI压缩: {original_tokens} -> {compressed_tokens} tokens "
            f"({total} -> {len(new_messages)} 条消息, "
            f"保留 {len(key_messages)} 条关键消息)"
        )

        return new_messages, summary

    # ============ HistoryStore 集成方法 ============

    def prepare_messages_for_api(
        self,
        messages: List[Dict],
        model_max_tokens: int = 180000,
    ) -> Tuple[List[Dict], bool]:
        """
        为 API 调用准备消息列表。
        如果超过阈值，自动进行本地压缩。

        Returns:
            (prepared_messages, was_compressed)
        """
        tokens = self.estimate_tokens(messages)

        if tokens <= self.COMPRESS_THRESHOLD:
            return messages, False

        logger.info(
            f"上下文 {tokens} tokens 超过阈值 {self.COMPRESS_THRESHOLD}，"
            f"自动本地压缩..."
        )

        target = min(self.COMPRESS_THRESHOLD, model_max_tokens // 2)
        compressed, summary = self.compress_local(messages, target_tokens=target)
        return compressed, True

    def update_history_store(
        self,
        history_store,
        bot_id: str,
        chat_id: int,
        compressed_messages: List[Dict],
    ):
        """
        将压缩后的消息写回 HistoryStore（替换原有历史）。
        这样下次获取历史时就是压缩后的版本。
        """
        try:
            # 清空旧历史
            history_store.clear_messages(bot_id, chat_id)
            # 写入压缩后的消息
            for msg in compressed_messages:
                content = msg.get("content", "")
                history_store.add_message(bot_id, chat_id, msg["role"], content)
            logger.info(
                f"已更新 HistoryStore: bot={bot_id}, chat={chat_id}, "
                f"messages={len(compressed_messages)}"
            )
        except Exception as e:
            logger.error(f"更新 HistoryStore 失败: {e}")

    # ============ 辅助方法 ============

    def _build_progressive_summary_prompt(
        self,
        normal_messages: List[Dict],
        key_messages: List[Dict],
    ) -> str:
        """构建渐进式摘要 prompt"""
        parts = []

        msgs_to_summarize = normal_messages[-30:]
        for msg in msgs_to_summarize:
            role = "用户" if msg["role"] == "user" else "助手"
            text = self._get_message_text(msg, max_len=200)
            if text.strip():
                parts.append(f"{role}: {text}")

        key_parts = []
        for msg in key_messages:
            role = "用户" if msg["role"] == "user" else "助手"
            text = self._get_message_text(msg, max_len=300)
            if text.strip():
                key_parts.append(f"[重要] {role}: {text}")

        prompt = "请总结以下对话的关键信息：\n\n"
        if key_parts:
            prompt += "=== 重要消息 ===\n" + "\n".join(key_parts) + "\n\n"
        prompt += "=== 对话内容 ===\n" + "\n".join(parts)

        return prompt

    def _simple_summary(self, messages: List[Dict]) -> str:
        """简单摘要（回退方案）"""
        parts = ["对话摘要:"]
        for msg in messages[-20:]:
            role = "用户" if msg["role"] == "user" else "助手"
            text = self._get_message_text(msg, max_len=80)
            if text.strip() and len(text) > 10:
                parts.append(f"- {role}: {text}...")
        return "\n".join(parts)

    def _save_summary(self, summary: str, original_messages: List[Dict]):
        """保存摘要到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data = {
            "timestamp": timestamp,
            "summary": summary,
            "message_count": len(original_messages),
        }
        filepath = self.storage_dir / f"summary_{timestamp}.json"
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存摘要失败: {e}")

    def extract_key_facts(self, messages: List[Dict]) -> List[str]:
        """提取关键事实"""
        facts = []
        for msg in messages:
            if self._is_key_message(msg):
                text = self._get_message_text(msg, max_len=150)
                if text:
                    facts.append(text)
        self.key_facts = facts[-10:]
        return self.key_facts

    def add_user_preference(self, key: str, value: Any):
        self.user_preferences[key] = value
        self._save_preferences()

    def _save_preferences(self):
        filepath = self.storage_dir / "preferences.json"
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.user_preferences, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存偏好失败: {e}")

    def load_preferences(self) -> Dict[str, Any]:
        filepath = self.storage_dir / "preferences.json"
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.user_preferences = json.load(f)
            except Exception as e:
                logger.error(f"加载偏好失败: {e}")
        return self.user_preferences

    def get_context_status(self, messages: List[Dict]) -> Dict[str, Any]:
        """获取上下文状态信息"""
        tokens = self.estimate_tokens(messages)
        return {
            "message_count": len(messages),
            "estimated_tokens": tokens,
            "max_tokens": self.MAX_CONTEXT_TOKENS,
            "compress_threshold": self.COMPRESS_THRESHOLD,
            "usage_percent": round(tokens / self.MAX_CONTEXT_TOKENS * 100, 1),
            "needs_compression": self.should_compress(messages),
            "must_compress": self.must_compress(messages),
            "has_summary": self.compressed_summary is not None,
            "key_facts_count": len(self.key_facts),
        }
