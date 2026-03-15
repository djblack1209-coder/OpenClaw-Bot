"""闲鱼 AI 多专家客服 — 定制化 OpenClaw 远程部署服务"""
import os
import re
import logging
from typing import Dict, List

from openai import OpenAI

logger = logging.getLogger(__name__)

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_prompt(name: str) -> str:
    for suffix in ("", "_example"):
        path = os.path.join(PROMPT_DIR, f"{name}{suffix}.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt {name} not found in {PROMPT_DIR}")


class BaseAgent:
    def __init__(self, client: OpenAI, system_prompt: str, model: str):
        self.client = client
        self.system_prompt = system_prompt
        self.model = model

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        messages = [
            {"role": "system", "content": f"【商品信息】{item_desc}\n【对话历史】{context}\n{self.system_prompt}"},
            {"role": "user", "content": user_msg},
        ]
        return self._call(messages)

    def _call(self, messages: List[Dict], temperature: float = 0.4) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=temperature, max_tokens=600, top_p=0.8,
        )
        return resp.choices[0].message.content


class PriceAgent(BaseAgent):
    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        temp = min(0.3 + bargain_count * 0.15, 0.9)
        messages = [
            {"role": "system", "content": f"【商品信息】{item_desc}\n【对话历史】{context}\n{self.system_prompt}\n▲当前议价轮次：{bargain_count}"},
            {"role": "user", "content": user_msg},
        ]
        return self._call(messages, temperature=temp)


class TechAgent(BaseAgent):
    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        messages = [
            {"role": "system", "content": f"【商品信息】{item_desc}\n【对话历史】{context}\n{self.system_prompt}"},
            {"role": "user", "content": user_msg},
        ]
        return self._call(messages, temperature=0.3)


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


BLOCKED = ["微信", "QQ", "支付宝", "银行卡", "线下交易"]


def _safe_filter(text: str) -> str:
    if any(p in text for p in BLOCKED):
        return "[安全提醒] 请通过闲鱼平台沟通交易，保障双方权益。"
    return text


class XianyuReplyBot:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("XIANYU_LLM_API_KEY", os.getenv("API_KEY", "")),
            base_url=os.getenv("XIANYU_LLM_BASE_URL", os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
        )
        self.model = os.getenv("XIANYU_LLM_MODEL", os.getenv("MODEL_NAME", "qwen-max"))
        self._load_agents()
        self.router = IntentRouter(self.agents["classify"])
        self.last_intent = None

    def _load_agents(self):
        self.agents = {
            "classify": BaseAgent(self.client, _load_prompt("classify_prompt"), self.model),
            "price": PriceAgent(self.client, _load_prompt("price_prompt"), self.model),
            "tech": TechAgent(self.client, _load_prompt("tech_prompt"), self.model),
            "default": BaseAgent(self.client, _load_prompt("default_prompt"), self.model),
        }

    def reload_prompts(self):
        self._load_agents()
        self.router = IntentRouter(self.agents["classify"])

    def generate_reply(self, user_msg: str, item_desc: str, context: List[Dict]) -> str:
        formatted = "\n".join(f"{m['role']}: {m['content']}" for m in context if m["role"] in ("user", "assistant"))
        intent = self.router.detect(user_msg, item_desc, formatted)

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

        reply = agent.generate(user_msg=user_msg, item_desc=item_desc, context=formatted, bargain_count=bargain_count)
        return _safe_filter(reply)
