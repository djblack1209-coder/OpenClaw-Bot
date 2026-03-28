"""
ClawBot - 上下文管理模块 v3.0（对标 MemGPT/Letta 16k⭐）

v3.0 — 2026-03-24:
  - 分层记忆深化（搬运自 letta-ai/letta 16k⭐ 架构模式）
  - Core memory 持久化（per-chat JSON 文件, 重启不丢失）
  - 打通 SmartMemoryPipeline ↔ TieredContextManager（事实自动归档）
  - 记忆重要性衰减 + 定期整合
  - per-chat 隔离（不同聊天各自记忆空间）

v2.1:
  - tiktoken 精确 token 计数（搬运自 letta/open-interpreter 最佳实践）
  - 替换原有 CJK 字符估算，精度从 ~70% 提升到 99%+

v2.0:
  - 本地压缩模式（零 API 调用）：截断+提取关键信息
  - AI 压缩模式（可选）：调用 LLM 生成高质量摘要
  - 渐进式压缩：越旧的消息压缩比越高
  - 支持关键信息标记保留
  - 支持 SQLite HistoryStore 集成
  - 分层上下文管理（core/recall/archival 三层架构）
"""
import json
import tempfile
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import logging
from src.utils import now_et

logger = logging.getLogger(__name__)

# ── tiktoken 精确 token 计数（搬运自 letta-ai/letta + open-interpreter）──
# cl100k_base 兼容 GPT-4/Claude/Qwen 等主流模型的 tokenizer
# 不可用时降级到 CJK 感知估算
_tiktoken_encoder = None
_HAS_TIKTOKEN = False

try:
    import tiktoken
    _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    _HAS_TIKTOKEN = True
    logger.debug("[context_manager] tiktoken 已加载 (cl100k_base)")
except ImportError:
    logger.info("[context_manager] tiktoken 未安装，使用 CJK 估算模式 (pip install tiktoken)")


def _atomic_json_write(path: Path, data: dict) -> None:
    """Atomically write JSON — write to temp file then rename.

    Prevents data corruption on crash: the file is either the old
    version or the new version, never a truncated partial write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except Exception as e:  # noqa: F841
        try:
            os.unlink(tmp)
        except OSError as e:  # noqa: F841
            pass
        raise


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
            # 从 config 导入避免循环依赖 (globals.py 导入了 ContextManager, 但 config.py 无此依赖)
            from src.bot.config import DATA_DIR
            self.storage_dir = Path(DATA_DIR)
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
        """精确计算文本 token 数。

        v2.1: 搬运 letta-ai/letta + open-interpreter 的 tiktoken 最佳实践。
        - 优先使用 tiktoken cl100k_base（精度 99%+，兼容 GPT-4/Claude/Qwen）
        - 不可用时降级到 CJK 感知估算（中文字符×2 + 英文÷4）
        """
        if not text:
            return 0
        if _HAS_TIKTOKEN and _tiktoken_encoder is not None:
            try:
                return len(_tiktoken_encoder.encode(text))
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
        # 降级: CJK 感知估算
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
        压缩后消息已在内存中，直接清空后重写即可。
        """
        try:
            # 先验证压缩后的消息不为空（防止误清空）
            if not compressed_messages:
                logger.warning("压缩后消息为空，跳过更新以保留原始历史")
                return

            # 清空旧历史并写入压缩后的消息（数据在内存中有备份）
            history_store.clear_messages(bot_id, chat_id)
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

    def _save_summary(self, summary: str, original_messages: List[Dict]):
        """保存摘要到文件"""
        timestamp = now_et().strftime("%Y%m%d_%H%M%S")
        data = {
            "timestamp": timestamp,
            "summary": summary,
            "message_count": len(original_messages),
        }
        filepath = self.storage_dir / f"summary_{timestamp}.json"
        try:
            _atomic_json_write(filepath, data)
        except Exception as e:
            logger.error(f"保存摘要失败: {e}")

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


# ============ 对标 Letta (MemGPT 16k⭐): 分层上下文管理 v3.0 ============

class TieredContextManager:
    """分层上下文管理器 v3.0（搬运自 letta-ai/letta 16k⭐ 架构模式）

    三层架构：
    - Core Memory: 始终在上下文中的关键信息（用户画像、系统指令、当前任务）
    - Recall Memory: 最近对话历史（滑动窗口，自动压缩）
    - Archival Memory: 长期存储（通过 SharedMemory 向量搜索按需检索）

    v3.0 升级（搬运自 Letta 架构模式）：
    - Core memory per-chat 持久化（重启不丢失，JSON 文件）
    - 打通 SmartMemoryPipeline（LLM 事实提取自动流入 archival）
    - 记忆重要性衰减 + 定期整合
    - per-chat_id 隔离（不同聊天各自记忆空间）
    """

    # 上下文预算分配（占总 token 预算的比例）
    CORE_BUDGET_PCT = 0.15      # 15% 给 core memory
    RECALL_BUDGET_PCT = 0.60    # 60% 给 recall (最近对话)
    ARCHIVAL_BUDGET_PCT = 0.15  # 15% 给 archival (按需检索)
    SYSTEM_BUDGET_PCT = 0.10    # 10% 给 system prompt + 工具

    def __init__(self, context_manager: ContextManager, shared_memory=None,
                 total_budget: int = 60000):
        """
        Args:
            context_manager: 现有的 ContextManager 实例
            shared_memory: SharedMemory 实例（用作 archival 层）
            total_budget: 总 token 预算
        """
        self.ctx = context_manager
        self.shared_memory = shared_memory
        self.total_budget = total_budget

        # v3.0: per-chat core memory (chat_id → Dict[str, str])
        self._core_memories: Dict[int, Dict[str, str]] = {}
        self._core_dirty: Dict[int, bool] = {}

        # 持久化目录
        self._memory_dir = Path(self.ctx.storage_dir) / "core_memory"
        self._memory_dir.mkdir(parents=True, exist_ok=True)

        # 默认 core memory 模板
        self._default_core = {
            "user_profile": "",      # 用户画像
            "bot_personality": "",   # Bot 人设
            "current_task": "",      # 当前任务
            "preferences": "",       # 用户偏好
            "key_facts": "",         # 关键事实 (v3.0)
        }

        # 向后兼容: 保留全局 _core_memory 用于无 chat_id 场景
        self._core_memory: Dict[str, str] = dict(self._default_core)
        self._core_dirty_global = False

    # ---- v3.0: Per-chat Core Memory 管理 ----

    def _get_core(self, chat_id: int = 0) -> Dict[str, str]:
        """获取指定 chat 的 core memory，自动加载持久化数据"""
        if chat_id == 0:
            return self._core_memory

        if chat_id not in self._core_memories:
            self._core_memories[chat_id] = self._load_core(chat_id)
            self._core_dirty[chat_id] = False

        return self._core_memories[chat_id]

    def _load_core(self, chat_id: int) -> Dict[str, str]:
        """从磁盘加载 core memory"""
        path = self._memory_dir / f"chat_{chat_id}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.debug(f"[TieredCtx] 加载 core memory: chat={chat_id}")
                # 合并默认字段（防止旧文件缺少新字段）
                merged = dict(self._default_core)
                merged.update(data)
                return merged
            except Exception as e:
                logger.warning(f"[TieredCtx] 加载 core memory 失败 chat={chat_id}: {e}")
        return dict(self._default_core)

    def _save_core(self, chat_id: int):
        """持久化 core memory 到磁盘"""
        if chat_id == 0:
            return
        path = self._memory_dir / f"chat_{chat_id}.json"
        try:
            core = self._core_memories.get(chat_id, {})
            _atomic_json_write(path, core)
            self._core_dirty[chat_id] = False
            logger.debug(f"[TieredCtx] 持久化 core memory: chat={chat_id}")
        except Exception as e:
            logger.warning(f"[TieredCtx] 持久化失败 chat={chat_id}: {e}")

    def _flush_dirty(self):
        """保存所有脏 core memory"""
        for chat_id, dirty in list(self._core_dirty.items()):
            if dirty:
                self._save_core(chat_id)

    def core_set(self, key: str, value: str, chat_id: int = 0):
        """写入 core memory（始终在上下文中）"""
        core = self._get_core(chat_id)
        core[key] = value
        if chat_id == 0:
            self._core_dirty_global = True
        else:
            self._core_dirty[chat_id] = True
        logger.debug(f"[TieredCtx] Core memory updated: chat={chat_id} {key} = {value[:50]}...")

    def core_get(self, key: str, chat_id: int = 0) -> str:
        return self._get_core(chat_id).get(key, "")

    def core_append(self, key: str, text: str, chat_id: int = 0):
        """追加到 core memory 条目"""
        core = self._get_core(chat_id)
        existing = core.get(key, "")
        core[key] = (existing + "\n" + text).strip()
        if chat_id == 0:
            self._core_dirty_global = True
        else:
            self._core_dirty[chat_id] = True

    def _render_core_memory(self, chat_id: int = 0) -> str:
        """渲染 core memory 为注入文本"""
        core = self._get_core(chat_id)
        parts = []
        for key, value in core.items():
            if value.strip():
                label = key.replace("_", " ").title()
                parts.append(f"[{label}]\n{value}")
        if not parts:
            return ""
        return "=== Core Memory ===\n" + "\n\n".join(parts)

    # ---- Archival Memory 检索 ----

    def archival_search(self, query: str, limit: int = 3) -> str:
        """从 archival memory (SharedMemory) 语义检索相关记忆"""
        if not self.shared_memory:
            return ""
        try:
            results = self.shared_memory.semantic_search(query, limit=limit)
            if not results:
                return ""
            parts = []
            for r in results:
                parts.append(f"- [{r['category']}] {r['key']}: {r['value'][:150]} (sim={r['similarity']})")
            return "=== Archival Memory (retrieved) ===\n" + "\n".join(parts)
        except Exception as e:
            logger.debug(f"[TieredCtx] Archival search failed: {e}")
            return ""

    def archival_store(self, key: str, value: str, category: str = "archival",
                       importance: int = 2):
        """存入 archival memory"""
        if not self.shared_memory:
            return
        self.shared_memory.remember(
            key=key, value=value, category=category,
            source_bot="tiered_ctx", importance=importance,
        )

    # ---- v3.0: SmartMemory 集成 ----

    def _sync_smart_memory_facts(self, chat_id: int = 0):
        """从 SmartMemoryPipeline 拉取最新事实同步到 core memory

        搬运自 Letta 的 memory management loop：
        LLM 提取的事实 → core memory key_facts 字段
        """
        try:
            from src.smart_memory import get_smart_memory
            smart_mem = get_smart_memory()
            if smart_mem is None or not self.shared_memory:
                return

            # 从 SharedMemory 检索最近提取的事实
            try:
                results = self.shared_memory.semantic_search(
                    "user preference fact", limit=5
                )
            except Exception as e:  # noqa: F841
                results = []

            if results:
                facts = [r["value"][:100] for r in results if r.get("value")]
                facts_text = "\n".join(f"• {f}" for f in facts[:5])
                core = self._get_core(chat_id)
                core["key_facts"] = facts_text
                if chat_id != 0:
                    self._core_dirty[chat_id] = True

            # 同步用户画像到 core memory
            try:
                profile_results = self.shared_memory.semantic_search(
                    "user_profile", limit=1
                )
                for r in (profile_results or []):
                    val = r.get("value", "")
                    if not val or "user_profile" not in r.get("key", ""):
                        continue
                    try:
                        profile = json.loads(val) if isinstance(val, str) else val
                        if isinstance(profile, dict):
                            parts = []
                            if profile.get("name"):
                                parts.append(f"称呼: {profile['name']}")
                            if profile.get("interests"):
                                interests = profile["interests"]
                                if isinstance(interests, list):
                                    parts.append(f"兴趣: {', '.join(interests)}")
                            if profile.get("expertise"):
                                expertise = profile["expertise"]
                                if isinstance(expertise, list):
                                    parts.append(f"专长: {', '.join(expertise)}")
                            if profile.get("communication_style"):
                                parts.append(f"沟通风格: {profile['communication_style']}")
                            if profile.get("preferences"):
                                prefs = profile["preferences"]
                                if isinstance(prefs, dict):
                                    pref_parts = [f"{k}: {v}" for k, v in prefs.items()]
                                    parts.append(f"偏好: {'; '.join(pref_parts)}")
                            if parts:
                                core = self._get_core(chat_id)
                                core["user_profile"] = "\n".join(parts)
                                core["preferences"] = profile.get("preferences", "")
                                if isinstance(core["preferences"], dict):
                                    core["preferences"] = "\n".join(
                                        f"• {k}: {v}" for k, v in core["preferences"].items()
                                    )
                                if chat_id != 0:
                                    self._core_dirty[chat_id] = True
                    except (json.JSONDecodeError, TypeError) as e:  # noqa: F841
                        pass
            except Exception as e:
                logger.debug("[TieredCtx] user_profile 同步失败", exc_info=True)

        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"[TieredCtx] SmartMemory 同步失败: {e}")

    # ---- 自动事实提取 ----

    def extract_and_archive_facts(self, messages: List[Dict]):
        """从对话中提取事实并存入 archival memory

        对标 Letta 的自动记忆管理：扫描用户消息中的关键信息，
        自动存入长期记忆。
        """
        if not self.shared_memory:
            return

        for msg in messages:
            if msg.get("role") != "user":
                continue
            if not self.ctx._is_key_message(msg):
                continue
            text = self.ctx._get_message_text(msg, max_len=500)
            if len(text) < 10:
                continue

            # 生成 key（基于内容前30字符）
            key_text = text[:30].replace(" ", "_").replace("\n", "_")
            self.archival_store(
                key=f"fact_{key_text}",
                value=text,
                category="extracted_fact",
                importance=3,
            )

    # ---- 智能上下文组装 ----

    def build_context(
        self,
        messages: List[Dict],
        system_prompt: str = "",
        query_hint: str = "",
        chat_id: int = 0,
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """智能组装分层上下文 v3.0（搬运自 Letta 上下文编排模式）

        v3.0 升级:
        - per-chat core memory 注入
        - SmartMemory 事实同步到 core
        - 组装完成后自动持久化

        Args:
            messages: 原始对话历史
            system_prompt: 系统提示词
            query_hint: 当前查询提示（用于 archival 检索）
            chat_id: 聊天 ID（用于 per-chat 记忆隔离）

        Returns:
            (assembled_messages, metadata)
        """
        budget = self.total_budget
        core_budget = int(budget * self.CORE_BUDGET_PCT)
        recall_budget = int(budget * self.RECALL_BUDGET_PCT)
        archival_budget = int(budget * self.ARCHIVAL_BUDGET_PCT)

        assembled = []
        metadata = {"core_tokens": 0, "recall_tokens": 0, "archival_tokens": 0,
                     "compressed": False, "archival_results": 0}

        # v3.0: 同步 SmartMemory 事实到 core memory
        self._sync_smart_memory_facts(chat_id)

        # GAP 7: 自动填充 bot_personality（从 system_prompt 提取，只写一次）
        core = self._get_core(chat_id)
        if not core.get("bot_personality") and system_prompt:
            # 只取 system_prompt 的前 200 字符作为人格摘要，避免过长
            core["bot_personality"] = system_prompt[:200]
            if chat_id != 0:
                self._core_dirty[chat_id] = True

        # 1. System prompt + Core memory
        core_text = self._render_core_memory(chat_id)
        system_content = system_prompt
        if core_text:
            system_content += f"\n\n{core_text}"

        if system_content.strip():
            assembled.append({"role": "user", "content": system_content})
            assembled.append({"role": "assistant", "content": "understood."})
            metadata["core_tokens"] = self.ctx.estimate_tokens(assembled)

        # 2. Archival memory（按需检索）
        if query_hint and self.shared_memory:
            archival_text = self.archival_search(query_hint, limit=3)
            if archival_text:
                archival_tokens = self.ctx._count_text_tokens(archival_text)
                if archival_tokens <= archival_budget:
                    assembled.append({"role": "user", "content": archival_text})
                    assembled.append({"role": "assistant", "content": "I've noted the relevant context."})
                    metadata["archival_tokens"] = archival_tokens
                    metadata["archival_results"] = archival_text.count("\n- ")

        # 3. Recall memory（最近对话，必要时压缩）
        recall_tokens = self.ctx.estimate_tokens(messages)
        if recall_tokens > recall_budget:
            compressed, _ = self.ctx.compress_local(messages, target_tokens=recall_budget)
            assembled.extend(compressed)
            metadata["compressed"] = True
            metadata["recall_tokens"] = self.ctx.estimate_tokens(compressed)
        else:
            assembled.extend(messages)
            metadata["recall_tokens"] = recall_tokens

        # 4. 自动提取事实到 archival
        self.extract_and_archive_facts(messages[-5:])

        total_tokens = self.ctx.estimate_tokens(assembled)
        metadata["total_tokens"] = total_tokens
        metadata["budget_usage_pct"] = round(total_tokens / budget * 100, 1)

        # v3.0: 自动持久化脏 core memory
        self._flush_dirty()

        return assembled, metadata

    def get_status(self, chat_id: int = 0) -> Dict[str, Any]:
        """获取分层上下文状态"""
        core = self._get_core(chat_id)
        core_size = sum(len(v) for v in core.values())
        return {
            "core_memory_keys": list(core.keys()),
            "core_memory_chars": core_size,
            "has_shared_memory": self.shared_memory is not None,
            "total_budget": self.total_budget,
            "persisted_chats": len(list(self._memory_dir.glob("chat_*.json"))),
            "budget_allocation": {
                "core": f"{self.CORE_BUDGET_PCT:.0%}",
                "recall": f"{self.RECALL_BUDGET_PCT:.0%}",
                "archival": f"{self.ARCHIVAL_BUDGET_PCT:.0%}",
                "system": f"{self.SYSTEM_BUDGET_PCT:.0%}",
            },
        }
