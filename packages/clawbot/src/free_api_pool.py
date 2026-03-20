"""
免费 LLM API 池 — 多源轮询 + 自动切换 + 健康检查
按模型强度分级，耗尽一个API自动切换下一个，每日扫描清理失效源。
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 模型强度分级: S > A > B > C
# S: 顶级推理（GPT-5, Claude Opus, Qwen3-235B）
# A: 强力通用（GPT-OSS-120B, Llama-3.3-70B, DeepSeek-V3, Mistral Medium）
# B: 中等能力（Qwen3-32B, Gemma-3-27B, Llama-4-Scout）
# C: 轻量快速（Llama-3.2-3B, Gemma-3-4B, 小模型）

TIER_S = "S"
TIER_A = "A"
TIER_B = "B"
TIER_C = "C"


@dataclass
class FreeAPISource:
    """一个免费API源"""
    provider: str           # openrouter / google / groq / cerebras / ...
    base_url: str
    api_key: str
    model: str              # 实际模型ID
    tier: str = TIER_B      # 强度等级
    daily_limit: int = 0    # 每日请求上限（0=无限）
    rpm_limit: int = 0      # 每分钟请求上限
    used_today: int = 0
    last_used: float = 0
    consecutive_errors: int = 0
    disabled: bool = False
    note: str = ""


@dataclass
class FreeAPIPool:
    """免费API池管理器"""
    sources: Dict[str, List[FreeAPISource]] = field(default_factory=dict)
    _state_path: str = ""

    def __post_init__(self):
        if not self._state_path:
            self._state_path = str(
                Path(__file__).parent.parent / "data" / "free_api_pool.json"
            )

    def add_source(self, model_family: str, source: FreeAPISource):
        """添加一个API源到指定模型族"""
        if model_family not in self.sources:
            self.sources[model_family] = []
        self.sources[model_family].append(source)
        logger.info(
            f"[FreePool] 添加 {source.provider}/{source.model} -> {model_family} (Tier {source.tier})"
        )

    def get_best_source(self, model_family: str, min_tier: str = TIER_C) -> Optional[FreeAPISource]:
        """获取最佳可用API源（按强度排序，跳过耗尽/禁用的）"""
        tier_order = {TIER_S: 0, TIER_A: 1, TIER_B: 2, TIER_C: 3}
        min_tier_val = tier_order.get(min_tier, 3)

        candidates = self.sources.get(model_family, [])
        # 按强度排序，同级按错误数排序
        candidates = sorted(
            candidates,
            key=lambda s: (tier_order.get(s.tier, 9), s.consecutive_errors)
        )

        for src in candidates:
            if src.disabled:
                continue
            if tier_order.get(src.tier, 9) > min_tier_val:
                continue
            if src.daily_limit > 0 and src.used_today >= src.daily_limit:
                continue
            if src.consecutive_errors >= 5:
                continue
            return src
        return None

    def get_any_source(self, min_tier: str = TIER_C) -> Optional[Tuple[str, FreeAPISource]]:
        """从所有模型族中获取最强可用源（用于 Free-LLM-Bot）
        
        排序策略：按 MODEL_RANKING 综合评分（强度+时新度）降序
        """
        tier_order = {TIER_S: 0, TIER_A: 1, TIER_B: 2, TIER_C: 3}
        min_tier_val = tier_order.get(min_tier, 3)

        all_sources = []
        for family, sources in self.sources.items():
            for src in sources:
                if not src.disabled and src.consecutive_errors < 5:
                    if src.daily_limit == 0 or src.used_today < src.daily_limit:
                        if tier_order.get(src.tier, 9) <= min_tier_val:
                            all_sources.append((family, src))

        # 使用 MODEL_RANKING 综合评分排序（延迟导入避免循环）
        all_sources.sort(
            key=lambda x: (
                -get_model_score(x[1].model),  # 综合评分降序
                x[1].consecutive_errors,         # 错误次数升序
            )
        )
        return all_sources[0] if all_sources else None

    def record_success(self, source: FreeAPISource):
        """记录成功调用"""
        source.used_today += 1
        source.last_used = time.time()
        source.consecutive_errors = 0

    def record_error(self, source: FreeAPISource, error: str = ""):
        """记录失败调用"""
        source.consecutive_errors += 1
        if source.consecutive_errors >= 5:
            logger.warning(
                f"[FreePool] {source.provider}/{source.model} 连续失败{source.consecutive_errors}次，暂时禁用"
            )

    def remove_exhausted(self):
        """清理已耗尽的API源"""
        removed = 0
        for family in list(self.sources.keys()):
            before = len(self.sources[family])
            self.sources[family] = [
                s for s in self.sources[family]
                if not (s.daily_limit > 0 and s.used_today >= s.daily_limit and s.consecutive_errors >= 3)
            ]
            removed += before - len(self.sources[family])
        if removed:
            logger.info(f"[FreePool] 清理了 {removed} 个耗尽的API源")
        return removed

    def reset_daily_counters(self):
        """每日重置计数器"""
        for family in self.sources.values():
            for src in family:
                src.used_today = 0
                src.consecutive_errors = 0
                src.disabled = False
        logger.info("[FreePool] 每日计数器已重置")

    def get_stats(self) -> Dict:
        """获取池状态统计"""
        total = sum(len(v) for v in self.sources.values())
        active = sum(
            1 for v in self.sources.values()
            for s in v if not s.disabled and s.consecutive_errors < 5
        )
        return {
            "total_sources": total,
            "active_sources": active,
            "model_families": len(self.sources),
            "families": {
                k: {"total": len(v), "active": sum(1 for s in v if not s.disabled)}
                for k, v in self.sources.items()
            }
        }

    def save_state(self):
        """持久化状态"""
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        data = {}
        for family, sources in self.sources.items():
            data[family] = [
                {
                    "provider": s.provider, "base_url": s.base_url,
                    "api_key": s.api_key, "model": s.model,
                    "tier": s.tier, "daily_limit": s.daily_limit,
                    "rpm_limit": s.rpm_limit, "used_today": s.used_today,
                    "consecutive_errors": s.consecutive_errors,
                    "disabled": s.disabled, "note": s.note,
                }
                for s in sources
            ]
        with open(self._state_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_state(self):
        """加载持久化状态"""
        if not os.path.exists(self._state_path):
            return
        try:
            with open(self._state_path) as f:
                data = json.load(f)
            for family, sources in data.items():
                self.sources[family] = [
                    FreeAPISource(**s) for s in sources
                ]
            logger.info(f"[FreePool] 加载了 {sum(len(v) for v in self.sources.values())} 个API源")
        except Exception as e:
            logger.error(f"[FreePool] 加载状态失败: {e}")


# ---- 全局单例 ----
free_pool = FreeAPIPool()


def init_free_pool():
    """初始化免费API池，加载已有状态或创建默认配置"""
    free_pool.load_state()

    # 如果池为空，加载默认免费源
    if not free_pool.sources:
        _load_default_sources()
        free_pool.save_state()

    stats = free_pool.get_stats()
    logger.info(
        f"[FreePool] 初始化完成: {stats['total_sources']}个源, "
        f"{stats['active_sources']}个活跃, {stats['model_families']}个模型族"
    )


def _load_default_sources():
    """
    加载默认免费API源（基于 cheahjs/free-llm-api-resources 项目）
    参考: https://github.com/cheahjs/free-llm-api-resources

    按优先级排列：
    1. SiliconFlow (无限, 国内延迟低)
    2. Groq (1000/天, 极速推理)
    3. Cerebras (14400/天, 极速推理)
    4. Google AI Studio (免费 Gemini)
    5. OpenRouter (50/天/模型, 品类丰富)
    6. Mistral (无限, 1RPM)
    7. Cohere (1000/月, Command R+)
    8. Cloudflare Workers AI (10000 neurons/天)
    9. GitHub Models (Copilot 用户)
    10. Kiro Gateway (本地免费 Claude)
    11. g4f (本地兜底)
    """

    # ---- 硅基流动免费模型 (优先级最高，国产无限免费) ----
    sf_keys = os.getenv("SILICONFLOW_KEYS", "").split(",")
    for i, key in enumerate(sf_keys):
        key = key.strip()
        if key:
            free_pool.add_source("qwen", FreeAPISource(
                provider=f"siliconflow_{i}", base_url="https://api.siliconflow.cn/v1",
                api_key=key, model="Qwen/Qwen3-235B-A22B",
                tier=TIER_S, daily_limit=0, rpm_limit=0,
                note="SiliconFlow free Qwen3-235B (无限)"
            ))
            # 硅基流动还有其他免费模型
            free_pool.add_source("deepseek", FreeAPISource(
                provider=f"siliconflow_{i}", base_url="https://api.siliconflow.cn/v1",
                api_key=key, model="deepseek-ai/DeepSeek-V3-0324",
                tier=TIER_S, daily_limit=0, rpm_limit=0,
                note="SiliconFlow free DeepSeek-V3 (无限)"
            ))
            free_pool.add_source("glm", FreeAPISource(
                provider=f"siliconflow_{i}", base_url="https://api.siliconflow.cn/v1",
                api_key=key, model="THUDM/GLM-4-32B-0414",
                tier=TIER_A, daily_limit=0, rpm_limit=0,
                note="SiliconFlow free GLM-4-32B (无限)"
            ))

    # ---- Groq (极速推理，免费层很大) ----
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        groq_models = [
            # (模型ID, 模型族, 等级, 日限, 分钟限)
            ("llama-3.3-70b-versatile", "llama", TIER_A, 1000, 30),
            ("meta-llama/llama-4-scout-17b-16e-instruct", "llama", TIER_B, 14400, 30),
            ("qwen/qwen3-32b", "qwen", TIER_B, 1000, 30),
            ("moonshotai/kimi-k2-instruct", "kimi", TIER_S, 1000, 30),
            ("deepseek-r1-distill-llama-70b", "deepseek", TIER_A, 1000, 30),
            ("compound-ai/compound-beta", "compound", TIER_A, 200, 20),
        ]
        for model, family, tier, dlimit, rlimit in groq_models:
            free_pool.add_source(family, FreeAPISource(
                provider="groq", base_url="https://api.groq.com/openai/v1",
                api_key=groq_key, model=model, tier=tier,
                daily_limit=dlimit, rpm_limit=rlimit,
                note="Groq free tier"
            ))

    # ---- Cerebras (极速推理, 14400/天) ----
    cerebras_key = os.getenv("CEREBRAS_API_KEY", "")
    if cerebras_key:
        free_pool.add_source("llama", FreeAPISource(
            provider="cerebras", base_url="https://api.cerebras.ai/v1",
            api_key=cerebras_key, model="llama-3.3-70b",
            tier=TIER_A, daily_limit=14400, rpm_limit=30,
            note="Cerebras free (极速, 2200 tok/s)"
        ))
        free_pool.add_source("llama", FreeAPISource(
            provider="cerebras", base_url="https://api.cerebras.ai/v1",
            api_key=cerebras_key, model="llama-4-scout-17b-16e-instruct",
            tier=TIER_B, daily_limit=14400, rpm_limit=30,
            note="Cerebras free Llama-4-Scout"
        ))

    # ---- Google AI Studio (Gemini 免费) ----
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        # Gemini 使用 OpenAI 兼容接口
        gemini_base = "https://generativelanguage.googleapis.com/v1beta/openai"
        free_pool.add_source("gemini", FreeAPISource(
            provider="google", base_url=gemini_base,
            api_key=gemini_key, model="gemini-2.5-flash",
            tier=TIER_S, daily_limit=500, rpm_limit=10,
            note="Google AI Studio free (最强免费推理)"
        ))
        free_pool.add_source("gemini", FreeAPISource(
            provider="google", base_url=gemini_base,
            api_key=gemini_key, model="gemini-2.0-flash",
            tier=TIER_A, daily_limit=1500, rpm_limit=15,
            note="Google AI Studio free"
        ))
        free_pool.add_source("gemini", FreeAPISource(
            provider="google", base_url=gemini_base,
            api_key=gemini_key, model="gemma-3-27b-it",
            tier=TIER_B, daily_limit=14400, rpm_limit=30,
            note="Google AI Studio free Gemma-3-27B"
        ))

    # ---- OpenRouter 免费模型 (品类丰富) ----
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    or_base = "https://openrouter.ai/api/v1"
    if or_key:
        or_models = [
            # (模型ID, 模型族, 等级)
            ("nousresearch/hermes-3-llama-3.1-405b:free", "llama", TIER_S),
            ("qwen/qwen3-235b-a22b:free", "qwen", TIER_S),
            ("qwen/qwen3-coder:free", "qwen", TIER_A),
            ("meta-llama/llama-3.3-70b-instruct:free", "llama", TIER_A),
            ("openai/gpt-oss-120b:free", "gpt-oss", TIER_A),
            ("deepseek/deepseek-r1-0528:free", "deepseek", TIER_S),
            ("google/gemma-3-27b-it:free", "gemma", TIER_B),
            ("mistralai/mistral-small-3.1-24b-instruct:free", "mistral", TIER_B),
            ("microsoft/phi-4-reasoning-plus:free", "phi", TIER_B),
            ("moonshotai/kimi-k2-instruct:free", "kimi", TIER_S),
        ]
        for model, family, tier in or_models:
            free_pool.add_source(family, FreeAPISource(
                provider="openrouter", base_url=or_base, api_key=or_key,
                model=model, tier=tier, daily_limit=50, rpm_limit=20,
                note="OpenRouter free tier"
            ))

    # ---- Mistral (无限量，但 1RPM) ----
    mistral_key = os.getenv("MISTRAL_API_KEY", "")
    if mistral_key:
        free_pool.add_source("mistral", FreeAPISource(
            provider="mistral", base_url="https://api.mistral.ai/v1",
            api_key=mistral_key, model="mistral-small-latest",
            tier=TIER_B, daily_limit=0, rpm_limit=1,
            note="Mistral Experiment (无限, 1RPM, 数据用于训练)"
        ))
        free_pool.add_source("mistral", FreeAPISource(
            provider="mistral_codestral", base_url="https://codestral.mistral.ai/v1",
            api_key=mistral_key, model="codestral-latest",
            tier=TIER_A, daily_limit=2000, rpm_limit=30,
            note="Mistral Codestral (代码专用, 2000/天)"
        ))

    # ---- Cohere (1000/月) ----
    cohere_key = os.getenv("COHERE_API_KEY", "")
    if cohere_key:
        free_pool.add_source("cohere", FreeAPISource(
            provider="cohere", base_url="https://api.cohere.com/v2",
            api_key=cohere_key, model="command-a-03-2025",
            tier=TIER_A, daily_limit=33, rpm_limit=20,
            note="Cohere free (Command A, ~33/天)"
        ))

    # ---- GitHub Models (需要 Copilot/GitHub Token) ----
    github_token = os.getenv("GITHUB_MODELS_TOKEN", "")
    if github_token:
        gh_models = [
            ("gpt-4.1-mini", "gpt", TIER_A),
            ("o4-mini", "gpt", TIER_S),
            ("DeepSeek-R1", "deepseek", TIER_S),
        ]
        for model, family, tier in gh_models:
            free_pool.add_source(family, FreeAPISource(
                provider="github_models", base_url="https://models.github.ai/inference",
                api_key=github_token, model=model, tier=tier,
                daily_limit=150, rpm_limit=15,
                note="GitHub Models (Copilot 用户)"
            ))

    # ---- Kiro Gateway (本地免费 Claude) ----
    kiro_key = os.getenv("KIRO_API_KEY", "")
    kiro_base = os.getenv("KIRO_BASE_URL", "http://127.0.0.1:18793/v1")
    if kiro_key:
        free_pool.add_source("claude", FreeAPISource(
            provider="kiro", base_url=kiro_base,
            api_key=kiro_key, model="claude-sonnet-4",
            tier=TIER_S, daily_limit=0, rpm_limit=5,
            note="Kiro Gateway 免费 Claude (本地)"
        ))

    # ---- NVIDIA NIM (需要手机验证) ----
    nvidia_key = os.getenv("NVIDIA_NIM_API_KEY", "")
    if nvidia_key:
        free_pool.add_source("llama", FreeAPISource(
            provider="nvidia", base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_key, model="meta/llama-3.3-70b-instruct",
            tier=TIER_A, daily_limit=0, rpm_limit=40,
            note="NVIDIA NIM free (需要手机验证)"
        ))

    # ---- Sambanova (免费试用) ----
    sambanova_key = os.getenv("SAMBANOVA_API_KEY", "")
    if sambanova_key:
        free_pool.add_source("deepseek", FreeAPISource(
            provider="sambanova", base_url="https://api.sambanova.ai/v1",
            api_key=sambanova_key, model="DeepSeek-R1",
            tier=TIER_S, daily_limit=100, rpm_limit=10,
            note="Sambanova free trial"
        ))

    # ---- g4f 本地（兜底，始终可用）----
    free_pool.add_source("g4f", FreeAPISource(
        provider="g4f", base_url="http://127.0.0.1:18891/v1",
        api_key="dummy", model="auto",
        tier=TIER_A, daily_limit=0, rpm_limit=0,
        note="g4f local (fallback, 始终可用)"
    ))


# ---- 模型强度+发布时间排序（用于 Free-LLM-Bot 轮询）----
# 综合评分 = 强度分 + 时新分。数值越高越优先。
# 强度基于公开 benchmark（Chatbot Arena, LMSYS 等）
# 时新分：2026年模型 +2, 2025年模型 +1, 更早 +0
MODEL_RANKING = {
    # --- S级 (前沿旗舰) ---
    "gemini-2.5-flash":        {"strength": 95, "recency": 2, "family": "gemini"},
    "claude-sonnet-4":         {"strength": 93, "recency": 2, "family": "claude"},
    "moonshotai/kimi-k2-instruct": {"strength": 92, "recency": 2, "family": "kimi"},
    "moonshotai/kimi-k2-instruct:free": {"strength": 92, "recency": 2, "family": "kimi"},
    "deepseek/deepseek-r1-0528:free": {"strength": 91, "recency": 2, "family": "deepseek"},
    "DeepSeek-R1":             {"strength": 91, "recency": 2, "family": "deepseek"},
    "o4-mini":                 {"strength": 90, "recency": 2, "family": "gpt"},
    "Qwen/Qwen3-235B-A22B":   {"strength": 90, "recency": 2, "family": "qwen"},
    "qwen/qwen3-235b-a22b:free": {"strength": 90, "recency": 2, "family": "qwen"},
    "nousresearch/hermes-3-llama-3.1-405b:free": {"strength": 89, "recency": 1, "family": "llama"},
    "deepseek-ai/DeepSeek-V3-0324": {"strength": 88, "recency": 2, "family": "deepseek"},
    # --- A级 (强力通用) ---
    "command-a-03-2025":       {"strength": 85, "recency": 2, "family": "cohere"},
    "gpt-4.1-mini":            {"strength": 84, "recency": 2, "family": "gpt"},
    "codestral-latest":        {"strength": 83, "recency": 2, "family": "mistral"},
    "llama-3.3-70b-versatile": {"strength": 82, "recency": 1, "family": "llama"},
    "llama-3.3-70b":           {"strength": 82, "recency": 1, "family": "llama"},
    "meta-llama/llama-3.3-70b-instruct:free": {"strength": 82, "recency": 1, "family": "llama"},
    "meta/llama-3.3-70b-instruct": {"strength": 82, "recency": 1, "family": "llama"},
    "deepseek-r1-distill-llama-70b": {"strength": 81, "recency": 1, "family": "deepseek"},
    "openai/gpt-oss-120b:free": {"strength": 80, "recency": 2, "family": "gpt-oss"},
    "compound-ai/compound-beta": {"strength": 80, "recency": 2, "family": "compound"},
    "qwen/qwen3-coder:free":   {"strength": 80, "recency": 2, "family": "qwen"},
    "gemini-2.0-flash":        {"strength": 80, "recency": 2, "family": "gemini"},
    "THUDM/GLM-4-32B-0414":   {"strength": 78, "recency": 2, "family": "glm"},
    # --- B级 (中等能力) ---
    "qwen/qwen3-32b":          {"strength": 75, "recency": 2, "family": "qwen"},
    "microsoft/phi-4-reasoning-plus:free": {"strength": 74, "recency": 2, "family": "phi"},
    "mistral-small-latest":    {"strength": 72, "recency": 2, "family": "mistral"},
    "mistralai/mistral-small-3.1-24b-instruct:free": {"strength": 72, "recency": 2, "family": "mistral"},
    "gemma-3-27b-it":          {"strength": 72, "recency": 2, "family": "gemma"},
    "google/gemma-3-27b-it:free": {"strength": 72, "recency": 2, "family": "gemma"},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"strength": 70, "recency": 2, "family": "llama"},
    "llama-4-scout-17b-16e-instruct": {"strength": 70, "recency": 2, "family": "llama"},
    # --- 兜底 ---
    "auto":                    {"strength": 65, "recency": 0, "family": "g4f"},
}


def get_model_score(model_id: str) -> float:
    """获取模型综合评分（强度 + 时新度），用于 Free-LLM-Bot 排序"""
    info = MODEL_RANKING.get(model_id)
    if info:
        return info["strength"] + info["recency"]
    return 50.0  # 未知模型给默认分


# ---- Bot 模型族映射 ----
BOT_MODEL_FAMILY = {
    "qwen235b": "qwen",
    "gptoss": "gpt-oss",
    "claude_sonnet": "g4f",      # Claude 模型走 g4f
    "claude_haiku": "g4f",
    "deepseek_v3": "g4f",
    "claude_opus": "g4f",
    "free_llm": None,            # Free-LLM-Bot: 用 get_any_source（按强度排序轮询）
}
