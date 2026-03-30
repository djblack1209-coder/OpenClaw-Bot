"""
智能记忆管道 — 搬运自 mem0ai/mem0 (50k⭐) 的核心模式
两阶段 LLM 管道：
  1. 事实提取：从对话中自动提取结构化事实
  2. 冲突解决：对每个新事实，LLM 决定 ADD/UPDATE/DELETE/NONE

适配 OpenClaw 多 Bot 架构：
  - 使用免费池 LLM（不额外花钱）
  - 异步非阻塞（不影响消息响应速度）
  - 与 SharedMemory 集成（不替换，增强）
"""
import json
import logging
import asyncio
import time
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from src.utils import emit_flow_event

logger = logging.getLogger(__name__)

# ── 事实提取 Prompt（搬运自 mem0 的 prompts.py，中文适配）──

FACT_EXTRACTION_PROMPT = """你是一个记忆提取器。从下面的对话中提取关键事实、偏好和决策。

规则：
1. 只提取明确陈述的事实，不要推测
2. 每条事实独立、简洁（一句话）
3. 包含：用户偏好、重要决策、关键数据、人名地名、待办事项
4. 忽略：寒暄、重复内容、AI 的客套话
5. 如果没有值得记住的内容，返回空数组

输出 JSON：
```json
{"facts": ["事实1", "事实2"]}
```

对话内容：
{conversation}"""

MEMORY_UPDATE_PROMPT = """你是一个记忆管理器。判断新事实与已有记忆的关系。

已有记忆：
{existing_memories}

新事实：{new_fact}

判断规则：
- ADD: 全新信息，与已有记忆不冲突
- UPDATE: 更新已有记忆（如偏好变化、数据更新），必须指定要更新的记忆 id
- DELETE: 新事实明确否定了某条已有记忆，必须指定要删除的记忆 id
- NONE: 已有记忆已包含此信息，无需操作

输出 JSON（只输出一个）：
```json
{"event": "ADD", "text": "要存储的文本"}
```
或
```json
{"event": "UPDATE", "id": "memory_key", "text": "更新后的文本", "old_text": "原文本"}
```
或
```json
{"event": "DELETE", "id": "memory_key"}
```
或
```json
{"event": "NONE"}
```"""

USER_PROFILE_PROMPT = """基于以下用户记忆，生成一份简洁的用户画像。

用户记忆：
{memories}

输出格式（JSON）：
```json
{{
  "name": "用户称呼",
  "interests": ["兴趣1", "兴趣2"],
  "preferences": {{"key": "value"}},
  "expertise": ["擅长领域"],
  "communication_style": "沟通风格描述",
  "summary": "一句话总结"
}}
```"""


@dataclass
class MemoryAction:
    """记忆操作"""
    event: str  # ADD / UPDATE / DELETE / NONE
    text: str = ""
    key: str = ""
    old_text: str = ""


class SmartMemoryPipeline:
    """智能记忆管道 — mem0 模式适配 OpenClaw
    
    核心思路：
    - 每 N 轮对话触发一次事实提取（异步，不阻塞回复）
    - 提取的事实与 SharedMemory 中已有记忆做冲突解决
    - 周期性生成用户画像（Tiger_bot 模式）
    """

    def __init__(
        self,
        shared_memory,
        llm_fn: Optional[Callable] = None,
        extract_interval: int = 5,
        profile_interval: int = 50,
    ):
        """
        Args:
            shared_memory: SharedMemory 实例
            llm_fn: async (prompt: str) -> str，LLM 调用函数
            extract_interval: 每 N 轮对话触发一次事实提取
            profile_interval: 每 N 轮对话更新一次用户画像
        """
        self.memory = shared_memory
        self.llm_fn = llm_fn
        self.extract_interval = extract_interval
        self.profile_interval = profile_interval
        self._turn_count: Dict[int, int] = {}  # chat_id -> turn count
        self._pending_messages: Dict[int, List[Dict]] = {}  # chat_id -> recent messages
        self._lock = asyncio.Lock()
        self._extracting: set = set()  # chat_ids currently running extraction
        self._last_extract_time: float = 0  # 全局限流: 防止多聊天并发触发 LLM 风暴
        self._extract_min_interval: float = 30.0  # 两次提取之间至少间隔 30 秒

    def set_llm_fn(self, llm_fn: Callable):
        """延迟设置 LLM 函数（启动后注入）"""
        self.llm_fn = llm_fn

    async def on_message(self, chat_id: int, user_id: int, role: str, content: str, bot_id: str = ""):
        """每条消息调用 — 累积消息，到达阈值时触发异步提取
        
        注意：dict 操作在 asyncio 单线程中是安全的，
        lock 仅保护 _extract_and_store 读取时的一致性。
        """
        # 无锁快速路径 — 累积消息和计数
        if chat_id not in self._pending_messages:
            self._pending_messages[chat_id] = []
        self._pending_messages[chat_id].append({
            "role": role, "content": content,
            "user_id": user_id, "bot_id": bot_id,
            "ts": time.time(),
        })
        # 只保留最近 20 条
        if len(self._pending_messages[chat_id]) > 20:
            self._pending_messages[chat_id] = self._pending_messages[chat_id][-20:]

        self._turn_count[chat_id] = self._turn_count.get(chat_id, 0) + 1
        turn = self._turn_count[chat_id]

        # 实时偏好检测 — 零 LLM 成本的正则捕获（搬运 ChatGPT Memory 模式）
        # 用户说"简短点"/"我喜欢..."/"以后别..."时立即写入记忆，不等 extract_interval
        if role == "user":
            _pref_t = asyncio.create_task(self._detect_instant_preference(content, chat_id, user_id, bot_id))
            _pref_t.add_done_callback(lambda t: t.exception() and logger.debug("偏好检测后台任务异常: %s", t.exception()))

        # 到达提取阈值 — 异步触发，不阻塞（跳过已在提取中的 chat + 全局限流）
        now_ts = time.time()
        if (turn % self.extract_interval == 0 and self.llm_fn
                and chat_id not in self._extracting
                and now_ts - self._last_extract_time >= self._extract_min_interval):
            self._extracting.add(chat_id)
            self._last_extract_time = now_ts
            _t = asyncio.create_task(self._extract_and_store(chat_id, user_id, bot_id))
            _t.add_done_callback(lambda t: (self._extracting.discard(chat_id), t.exception() and logger.debug("事实提取后台任务异常: %s", t.exception())))

        # 到达画像更新阈值
        if turn % self.profile_interval == 0 and self.llm_fn:
            _t2 = asyncio.create_task(self._update_user_profile(chat_id, user_id))
            _t2.add_done_callback(lambda t: t.exception() and logger.debug("用户画像更新后台任务异常: %s", t.exception()))

    async def _detect_instant_preference(self, content: str, chat_id: int, user_id: int, bot_id: str):
        """实时偏好检测器 — 零 LLM 成本捕获用户偏好信号

        搬运灵感: ChatGPT Memory 的 "Remembered" 功能 / mem0 auto-extract
        当检测到偏好信号词时，立即写入 SharedMemory，不等 extract_interval。
        """
        import re
        try:
            text = (content or "").strip()
            if len(text) < 4:
                return

            # 偏好信号词匹配（优先级从高到低）
            _PREF_PATTERNS = [
                # 直接表达偏好
                (r"(?:我喜欢|我偏好|我倾向|我更想)", "用户偏好"),
                # 负面偏好
                (r"(?:我讨厌|别给我|不要给我|我不喜欢|以后别|以后不要)", "用户反感"),
                # 沟通风格
                (r"(?:简短[点些一]|简洁[点些一]|少[说废]话|直接[说给]|别[啰罗]嗦)", "沟通风格: 偏好简洁"),
                (r"(?:详细[点些一]|说[详仔]细|展开[说讲])", "沟通风格: 偏好详细"),
                # 记住/记住了
                (r"(?:帮我记住|你记一下|记住我|以后记得)", "用户要求记忆"),
            ]

            matched_category = None
            for pattern, category in _PREF_PATTERNS:
                if re.search(pattern, text):
                    matched_category = category
                    break

            if not matched_category:
                return

            # 立即写入 SharedMemory（不等定期提取），传入 chat_id 确保用户隔离
            if self.memory:
                pref_fact = f"[{matched_category}] {text[:100]}"
                self.memory.remember(
                    key=pref_fact,
                    value=text[:200],
                    category="user_preference",
                    importance=5,
                    chat_id=chat_id,
                )
                logger.info(f"💬 实时偏好捕获: {pref_fact[:60]}")

                # 偏好变化 → 触发画像立即更新（不等 profile_interval）
                if self.llm_fn:
                    asyncio.create_task(self._update_user_profile(chat_id, user_id))

        except Exception as e:
            logger.debug(f"实时偏好检测异常 (不影响主流程): {e}")

    async def _extract_and_store(self, chat_id: int, user_id: int, bot_id: str):
        """阶段1: LLM 事实提取 + 阶段2: 冲突解决（搬运自 mem0）"""
        if not self.llm_fn:
            return
        try:
            # 快照消息（无锁，asyncio 单线程安全）
            messages = list(self._pending_messages.get(chat_id, []))
            if len(messages) < 2:
                return

            # 阶段1: 提取事实
            conversation = "\n".join(
                f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:300]}"
                for m in messages[-10:]
            )
            prompt = FACT_EXTRACTION_PROMPT.format(conversation=conversation)
            response = await asyncio.wait_for(self.llm_fn(prompt), timeout=30)
            facts = self._parse_facts(response)

            if not facts:
                return

            logger.info(f"[SmartMemory] chat={chat_id} 提取到 {len(facts)} 条事实")
            emit_flow_event("llm", "mem0", "running", f"提取到 {len(facts)} 条新事实", {"facts": facts})

            # 阶段2: 对每条事实做冲突解决
            for fact in facts[:5]:  # 限制每轮最多处理 5 条
                await self._resolve_and_store(fact, chat_id, user_id, bot_id)

        except asyncio.TimeoutError as e:
            logger.debug(f"[SmartMemory] 事实提取超时 (chat={chat_id})")
        except Exception as e:
            logger.warning(f"[SmartMemory] 事实提取失败 (chat={chat_id}): {e}")

    async def _resolve_and_store(self, fact: str, chat_id: int, user_id: int, bot_id: str):
        """对单条事实做冲突解决 — 搬运自 mem0 的 update memory 流程"""
        if not self.llm_fn:
            return
        try:
            # 搜索相关已有记忆
            # SharedMemory.search() 返回 {"success": bool, "results": [...], "count": int}
            search_result = self.memory.search(fact, limit=5)
            existing = search_result.get("results", []) if isinstance(search_result, dict) else []
            if not existing:
                # 无相关记忆，直接 ADD
                key = f"auto_{user_id}_{int(time.time())}"
                self.memory.remember(key, fact, source_bot=bot_id, importance=3)
                logger.debug(f"[SmartMemory] ADD: {fact[:60]}")
                emit_flow_event("mem0", "db", "success", "存储新记忆", {"action": "ADD", "fact": fact})
                return

            # 格式化已有记忆
            existing_text = "\n".join(
                f"- id: {m.get('key', '')}, 内容: {m.get('value', '')[:100]}"
                for m in existing
            )

            prompt = MEMORY_UPDATE_PROMPT.format(
                existing_memories=existing_text,
                new_fact=fact,
            )
            response = await asyncio.wait_for(self.llm_fn(prompt), timeout=20)
            action = self._parse_action(response)

            if action.event == "ADD":
                key = f"auto_{user_id}_{int(time.time())}"
                self.memory.remember(key, action.text or fact, source_bot=bot_id, importance=3)
                logger.debug(f"[SmartMemory] ADD: {(action.text or fact)[:60]}")
                emit_flow_event("mem0", "db", "success", "追加记忆", {"action": "ADD", "fact": action.text or fact})

            elif action.event == "UPDATE" and action.key:
                self.memory.remember(action.key, action.text, source_bot=bot_id, importance=4)
                logger.debug(f"[SmartMemory] UPDATE {action.key}: {action.text[:60]}")
                emit_flow_event("mem0", "db", "success", "更新记忆", {"action": "UPDATE", "key": action.key, "text": action.text})

            elif action.event == "DELETE" and action.key:
                self.memory.forget(action.key)
                logger.debug(f"[SmartMemory] DELETE: {action.key}")
                emit_flow_event("mem0", "db", "success", "删除冲突记忆", {"action": "DELETE", "key": action.key})

            # NONE: 不操作

        except asyncio.TimeoutError as e:
            logger.debug(f"[SmartMemory] 冲突解决超时: {fact[:40]}")
        except Exception as e:
            logger.debug(f"[SmartMemory] 冲突解决失败: {e}")

    async def _update_user_profile(self, chat_id: int, user_id: int):
        """周期性用户画像更新 — 搬运自 Tiger_bot 的反思循环"""
        if not self.llm_fn:
            return
        try:
            # 获取该用户的所有记忆
            search_result = self.memory.search(f"user_{user_id}", limit=20)
            all_memories = search_result.get("results", []) if isinstance(search_result, dict) else []
            if len(all_memories) < 3:
                return

            memories_text = "\n".join(
                f"- {m.get('value', '')[:150]}" for m in all_memories
            )
            prompt = USER_PROFILE_PROMPT.format(memories=memories_text)
            response = await asyncio.wait_for(self.llm_fn(prompt), timeout=30)

            # 解析并存储用户画像
            profile = self._parse_json(response)
            if profile:
                self.memory.remember(
                    f"user_profile_{user_id}",
                    json.dumps(profile, ensure_ascii=False),
                    source_bot="system",
                    importance=5,
                )
                logger.info(f"[SmartMemory] 用户画像已更新: user={user_id}")
                emit_flow_event("mem0", "profile", "success", "用户画像更新", {"profile": profile})

                # 同步画像到 TieredContextManager core memory
                try:
                    from src.bot.globals import tiered_context_manager as _tcm
                    if _tcm and profile:
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
                        if parts:
                            profile_text = "\n".join(parts)
                            _tcm.core_set("user_profile", profile_text, chat_id=chat_id)
                            logger.info("[SmartMemory] 画像已同步到 TieredContextManager core memory")
                except Exception as tcm_e:
                    logger.debug(f"[SmartMemory] 同步到 TCM 失败: {tcm_e}")

                # 自动将画像同步写入硬盘的 MEMORY.md 供人类（严总）阅读
                try:
                    import os
                    from pathlib import Path
                    ws_dir = os.environ.get("OPENCLAW_WORKSPACE", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "apps", "openclaw"))
                    memory_file = Path(ws_dir) / "MEMORY.md"
                    
                    if memory_file.exists():
                        with open(memory_file, 'r', encoding='utf-8') as mf:
                            mf_content = mf.read()
                        
                        # 如果没有智能画像块，创建一个
                        if "## 🧠 Agentic Smart Profile" not in mf_content:
                            mf_content += "\n\n## 🧠 Agentic Smart Profile\n\n"
                            
                        # 用正则替换掉旧的画像块
                        import re
                        profile_md = f"**Last Updated**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        profile_md += f"**Name**: {profile.get('name', '严总')}\n"
                        profile_md += f"**Interests**: {', '.join(profile.get('interests', []))}\n"
                        for k, v in profile.get('preferences', {}).items():
                            profile_md += f"- **{k}**: {v}\n"
                        
                        new_content = re.sub(
                            r"## 🧠 Agentic Smart Profile[\s\S]*?(?=\n## |$)", 
                            f"## 🧠 Agentic Smart Profile\n\n{profile_md}\n\n", 
                            mf_content
                        )
                        
                        with open(memory_file, 'w', encoding='utf-8') as mf:
                            mf.write(new_content)
                            
                        logger.info("[SmartMemory] 已将最新用户画像同步至 MEMORY.md")
                        emit_flow_event("mem0", "file", "success", "更新 MEMORY.md 文件", {"file": "MEMORY.md"})
                except Exception as sync_e:
                    logger.warning(f"[SmartMemory] 同步至 MEMORY.md 失败: {sync_e}")


        except asyncio.TimeoutError as e:
            logger.debug(f"[SmartMemory] 用户画像更新超时: user={user_id}")
        except Exception as e:
            logger.warning(f"[SmartMemory] 用户画像更新失败: {e}")

    # ── 解析工具 ──

    @staticmethod
    def _parse_facts(response: str) -> List[str]:
        """从 LLM 响应中解析事实列表"""
        try:
            data = SmartMemoryPipeline._parse_json(response)
            if isinstance(data, dict) and "facts" in data:
                return [f for f in data["facts"] if isinstance(f, str) and len(f) > 5]
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        return []

    @staticmethod
    def _parse_action(response: str) -> MemoryAction:
        """从 LLM 响应中解析记忆操作"""
        try:
            data = SmartMemoryPipeline._parse_json(response)
            if isinstance(data, dict):
                return MemoryAction(
                    event=data.get("event", "NONE").upper(),
                    text=data.get("text", ""),
                    key=data.get("id", ""),
                    old_text=data.get("old_text", ""),
                )
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        return MemoryAction(event="NONE")

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """从可能包含 markdown 代码块的文本中提取 JSON（使用 json_repair 容错）"""
        import re
        from json_repair import loads as jloads
        # 尝试直接解析（json_repair 自动修复尾逗号、缺引号等）
        try:
            result = jloads(text)
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        # 尝试从代码块中提取
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                result = jloads(match.group(1))
                if isinstance(result, dict):
                    return result
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
        # 尝试找匹配的 { ... }（支持嵌套大括号）
        depth = 0
        start_idx = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start_idx >= 0:
                    try:
                        result = jloads(text[start_idx:i + 1])
                        if isinstance(result, dict):
                            return result
                    except Exception as e:  # noqa: F841
                        start_idx = -1
        return None

    def get_user_profile(self, user_id: int) -> Optional[dict]:
        """获取用户画像"""
        search_result = self.memory.search(f"user_profile_{user_id}", limit=1)
        results = search_result.get("results", []) if isinstance(search_result, dict) else []
        if results:
            try:
                return json.loads(results[0].get("value", "{}"))
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
        return None

    def get_stats(self) -> dict:
        """获取管道统计"""
        return {
            "active_chats": len(self._turn_count),
            "total_turns": sum(self._turn_count.values()),
            "pending_messages": sum(len(v) for v in self._pending_messages.values()),
        }


# 全局实例
smart_memory: Optional[SmartMemoryPipeline] = None


def init_smart_memory(shared_memory, llm_fn=None) -> SmartMemoryPipeline:
    """初始化智能记忆管道"""
    global smart_memory
    smart_memory = SmartMemoryPipeline(shared_memory, llm_fn)
    logger.info("[SmartMemory] 智能记忆管道已初始化 (mem0 模式)")
    return smart_memory


def get_smart_memory() -> Optional[SmartMemoryPipeline]:
    return smart_memory
