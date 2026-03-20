"""闲鱼 AI 多专家客服 — LiteLLM Router 版

升级:
- 替代独立 OpenAI client，统一走 LiteLLM Router (fallback + 多 provider)
- 保持多专家架构: IntentRouter + PriceAgent + TechAgent + DefaultAgent
- 新增: 异步调用支持 (async generate)
"""
import asyncio
import os
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_prompt(name: str) -> str:
    for suffix in ("", "_example"):
        path = os.path.join(PROMPT_DIR, f"{name}{suffix}.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt {name} not found in {PROMPT_DIR}")


# ---- 安全过滤 ----
BLOCKED = ["微信", "QQ", "支付宝", "银行卡", "线下交易"]


def _safe_filter(text: str) -> str:
    if any(p in text for p in BLOCKED):
        return "[安全提醒] 请通过闲鱼平台沟通交易，保障双方权益。"
    return text


# ---- Agent 基类 ----

class BaseAgent:
    def __init__(self, system_prompt: str, model_family: str = "qwen"):
        self.system_prompt = system_prompt
        self.model_family = model_family

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        """同步调用 (兼容旧代码)"""
        return asyncio.get_event_loop().run_until_complete(
            self.agenerate(user_msg, item_desc, context, bargain_count)
        )

    async def agenerate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        """异步调用 — 走 LiteLLM Router"""
        system = f"【商品信息】{item_desc}\n【对话历史】{context}\n{self.system_prompt}"
        messages = [{"role": "user", "content": user_msg}]
        return await self._acall(messages, system, temperature=0.4)

    async def _acall(self, messages: List[Dict], system: str = "", temperature: float = 0.4) -> str:
        from src.litellm_router import free_pool
        try:
            response = await free_pool.acompletion(
                model_family=self.model_family,
                messages=messages,
                system_prompt=system or self.system_prompt,
                temperature=temperature,
                max_tokens=600,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"[XianyuAgent] LLM 调用失败: {e}")
            return "抱歉，系统繁忙，请稍后再试。"


class PriceAgent(BaseAgent):
    async def agenerate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        temp = min(0.3 + bargain_count * 0.15, 0.9)
        system = (
            f"【商品信息】{item_desc}\n【对话历史】{context}\n"
            f"{self.system_prompt}\n▲当前议价轮次：{bargain_count}"
        )
        messages = [{"role": "user", "content": user_msg}]
        return await self._acall(messages, system, temperature=temp)


class TechAgent(BaseAgent):
    async def agenerate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        system = f"【商品信息】{item_desc}\n【对话历史】{context}\n{self.system_prompt}"
        messages = [{"role": "user", "content": user_msg}]
        return await self._acall(messages, system, temperature=0.3)


# ---- 意图路由 ----

class IntentRouter:
    RULES = {
        "tech": {
            "keywords": ["怎么装", "怎么用", "部署", "安装", "配置", "系统", "win", "mac", "linux", "docker",
                         "api", "模型", "skill", "agent", "mcp", "报错", "错误", "bug", "问题"],
            "patterns": [r"怎么.+装", r"如何.+配", r"支持.+系统"],
        },
        "price": {
            "keywords": ["便宜", "价", "砍价", "少点", "优惠", "打折", "包邮"],
            "patterns": [r"\d+元", r"能少\d+"],
        },
    }

    def __init__(self, classify_agent: BaseAgent):
        self.classify_agent = classify_agent

    def detect(self, user_msg: str, item_desc: str, context: str) -> str:
        clean = re.sub(r"[^\w\u4e00-\u9fa5]", "", user_msg).lower()
        for intent in ("tech", "price"):
            if any(kw in clean for kw in self.RULES[intent]["keywords"]):
                return intent
            if any(re.search(p, clean) for p in self.RULES[intent]["patterns"]):
                return intent
        # LLM fallback
        return self.classify_agent.generate(user_msg=user_msg, item_desc=item_desc, context=context)

    async def adetect(self, user_msg: str, item_desc: str, context: str) -> str:
        """异步意图检测"""
        clean = re.sub(r"[^\w\u4e00-\u9fa5]", "", user_msg).lower()
        for intent in ("tech", "price"):
            if any(kw in clean for kw in self.RULES[intent]["keywords"]):
                return intent
            if any(re.search(p, clean) for p in self.RULES[intent]["patterns"]):
                return intent
        return await self.classify_agent.agenerate(user_msg=user_msg, item_desc=item_desc, context=context)


# ---- 主 Bot ----

class XianyuReplyBot:
    def __init__(self):
        # 从环境变量读取模型族偏好，默认 qwen (免费)
        self.model_family = os.getenv("XIANYU_MODEL_FAMILY", "qwen")
        self._load_agents()
        self.router = IntentRouter(self.agents["classify"])
        self.last_intent: Optional[str] = None

    def _load_agents(self):
        fam = self.model_family
        self.agents = {
            "classify": BaseAgent(_load_prompt("classify_prompt"), fam),
            "price": PriceAgent(_load_prompt("price_prompt"), fam),
            "tech": TechAgent(_load_prompt("tech_prompt"), fam),
            "default": BaseAgent(_load_prompt("default_prompt"), fam),
        }

    def reload_prompts(self):
        self._load_agents()
        self.router = IntentRouter(self.agents["classify"])

    def generate_reply(self, user_msg: str, item_desc: str, context: List[Dict]) -> str:
        """同步接口 (兼容旧调用)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run, self.agenerate_reply(user_msg, item_desc, context)
                    ).result(timeout=30)
            return loop.run_until_complete(self.agenerate_reply(user_msg, item_desc, context))
        except Exception as e:
            logger.error(f"[XianyuReplyBot] sync generate failed: {e}")
            return "抱歉，系统繁忙，请稍后再试。"

    async def agenerate_reply(self, user_msg: str, item_desc: str, context: List[Dict]) -> str:
        """异步接口 — 推荐使用"""
        formatted = "\n".join(f"{m['role']}: {m['content']}" for m in context if m["role"] in ("user", "assistant"))
        intent = await self.router.adetect(user_msg, item_desc, formatted)

        if intent == "no_reply":
            self.last_intent = "no_reply"
            return "-"

        agent = self.agents.get(intent, self.agents["default"])
        if intent == "classify":
            agent = self.agents["default"]
        self.last_intent = intent

        bargain_count = 0
        for m in context:
            if m["role"] == "system" and "议价次数" in m["content"]:
                match = re.search(r"议价次数[:：]\s*(\d+)", m["content"])
                if match:
                    bargain_count = int(match.group(1))

        reply = await agent.agenerate(
            user_msg=user_msg, item_desc=item_desc,
            context=formatted, bargain_count=bargain_count,
        )
        return _safe_filter(reply)
