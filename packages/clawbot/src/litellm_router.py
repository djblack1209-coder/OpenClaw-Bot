"""
LiteLLM 统一路由层 — 替代自研 free_api_pool.py (935行 → ~450行)

核心升级:
- LiteLLM Router: 100+ provider、自动 fallback、cooldown、cost tracking
- 保持旧接口兼容: free_pool.get_best_source() / get_stats() 等
- 零额外进程: 嵌入现有 Python 进程

对标: LiteLLM (39.6k⭐), Portkey Gateway (11k⭐)
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import litellm
from litellm.router import Router

logger = logging.getLogger(__name__)

# ---- LLM 缓存层 (diskcache, graceful degradation) ----
try:
    from src.llm_cache import _make_cache_key, _get_cache
    _HAS_LLM_CACHE = True

    def _llm_cache_get(key: str):
        cache = _get_cache()
        if cache is None:
            return None
        from src.llm_cache import _stats
        val = cache.get(key)
        if val is not None:
            _stats["hits"] += 1
        else:
            _stats["misses"] += 1
        return val

    def _llm_cache_set(key: str, value, ttl: int):
        cache = _get_cache()
        if cache is not None:
            cache.set(key, value, expire=ttl)

except ImportError:
    _HAS_LLM_CACHE = False

    def _llm_cache_get(key: str):  # type: ignore[misc]
        return None

    def _llm_cache_set(key: str, value, ttl: int):  # type: ignore[misc]
        pass

    def _make_cache_key(*args, **kwargs) -> str:  # type: ignore[misc]
        return ""

# 静默 LiteLLM 内部日志
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("LiteLLM Router").setLevel(logging.WARNING)
logging.getLogger("LiteLLM Proxy").setLevel(logging.WARNING)
litellm.suppress_debug_info = True

# ---- Langfuse 自动集成 ----
# LiteLLM 原生支持 langfuse callback，只需设置 success_callback
# 当 LANGFUSE_SECRET_KEY 存在时自动启用
if os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"):
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
    logger.info("[LiteLLM] Langfuse callback 已启用")

# ---- 路由策略常量 (兼容旧代码 import) ----
ROUTE_STRONGEST = "strongest"
ROUTE_LOWEST_LATENCY = "lowest-latency"
ROUTE_LEAST_BUSY = "least-busy"
ROUTE_COST_OPTIMIZED = "cost-optimized"
ROUTE_BALANCED = "balanced"

# ---- 模型强度分级 ----
TIER_S, TIER_A, TIER_B, TIER_C = "S", "A", "B", "C"
_TIER_ORDER = {TIER_S: 0, TIER_A: 1, TIER_B: 2, TIER_C: 3}


@dataclass
class FreeAPISource:
    """兼容层: 保持旧接口，内部映射到 LiteLLM deployment"""
    provider: str
    base_url: str
    api_key: str
    model: str
    tier: str = TIER_B
    daily_limit: int = 0
    rpm_limit: int = 0
    used_today: int = 0
    last_used: float = 0
    consecutive_errors: int = 0
    disabled: bool = False
    note: str = ""
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    tpm_limit: int = 0
    max_concurrent: int = 0
    _deployment_id: str = ""

    def can_accept_request(self) -> bool:
        if self.disabled or self.consecutive_errors >= 5:
            return False
        if self.daily_limit > 0 and self.used_today >= self.daily_limit:
            return False
        return True


# ---- 模型强度排名 ----
MODEL_RANKING = {
    "gemini-2.5-pro": 98, "gemini-2.5-flash": 97, "claude-sonnet-4": 95,
    "gemini-3-flash-preview": 95,
    "moonshotai/kimi-k2-instruct": 94, "moonshotai/kimi-k2-instruct:free": 94,
    "deepseek/deepseek-r1-0528:free": 93, "DeepSeek-R1": 93, "deepseek-r1": 93,
    "o4-mini": 92, "Qwen/Qwen3-235B-A22B": 92, "qwen/qwen3-235b-a22b:free": 92,
    "qwen3-235b-a22b-instruct": 92,
    "nousresearch/hermes-3-llama-3.1-405b:free": 90,
    "deepseek-ai/DeepSeek-V3-0324": 90, "deepseek-v3.2": 90, "deepseek-v3": 88,
    "command-a-reasoning-08-2025": 89, "command-a-vision-07-2025": 87,
    "command-a-03-2025": 87, "gpt-4.1-mini": 86, "codestral-latest": 85,
    "kimi-k2": 94, "qwen3-max": 91, "qwen3-coder-plus": 90,
    "llama-3.3-70b-versatile": 83, "llama-3.3-70b": 83,
    "meta-llama/llama-3.3-70b-instruct:free": 83, "meta/llama-3.3-70b-instruct": 83,
    "deepseek-r1-distill-llama-70b": 82,
    "openai/gpt-oss-120b:free": 82, "compound-ai/compound-beta": 82,
    "qwen/qwen3-coder:free": 82, "gemini-2.0-flash": 82,
    "gemini-2.5-flash-lite": 80,
    "THUDM/GLM-4-32B-0414": 80,
    "qwen/qwen3-32b": 77, "qwen3-32b": 77,
    "microsoft/phi-4-reasoning-plus:free": 76,
    "mistral-small-latest": 74, "mistralai/mistral-small-3.1-24b-instruct:free": 74,
    "gemma-3-27b-it": 74, "google/gemma-3-27b-it:free": 74,
    "meta-llama/llama-4-scout-17b-16e-instruct": 72,
    "llama-4-scout-17b-16e-instruct": 72,
    "nvidia/nemotron-3-super-120b-a12b:free": 90,
    "minimax/minimax-m2.5:free": 88,
    "qwen/qwen3-next-80b-a3b-instruct:free": 85,
    "gpt-4o": 88, "gpt-4o-mini": 78,
    "auto": 65,
}


def get_model_score(model_id: str) -> float:
    return MODEL_RANKING.get(model_id, 50.0)


BOT_MODEL_FAMILY = {
    "qwen235b": "qwen", "gptoss": "gpt-oss",
    "claude_sonnet": "g4f", "claude_haiku": "g4f",
    "deepseek_v3": "g4f", "claude_opus": "g4f",
    "free_llm": None,
}


# ============================================================
# LiteLLMPool
# ============================================================

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_list(key: str) -> List[str]:
    return [k.strip() for k in _env(key).split(",") if k.strip()]


class LiteLLMPool:
    """LiteLLM Router 封装，对外保持 FreeAPIPool 兼容接口。"""

    def __init__(self):
        self._router: Optional[Router] = None
        self._sources: Dict[str, List[FreeAPISource]] = {}
        self.default_routing: str = ROUTE_BALANCED
        self._call_count = 0
        self._error_count = 0
        self._total_latency = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0

        # Phoenix OTEL — 与 Langfuse 并行运行，OpenTelemetry 标准协议
        try:
            from src.observability import init_phoenix
            init_phoenix()
        except ImportError:
            pass

    @property
    def sources(self) -> Dict[str, List[FreeAPISource]]:
        return self._sources

    def _reg(self, family: str, src: FreeAPISource):
        self._sources.setdefault(family, []).append(src)

    def _dep(self, name: str, model: str, key: str,
             base: str = "", rpm: int = 0, tier: str = TIER_B,
             family: str = "", note: str = "") -> Dict:
        """创建一个 LiteLLM deployment + 注册 FreeAPISource"""
        dep_id = f"{name}/{model}"
        params: Dict[str, Any] = {"model": model, "api_key": key}
        if base:
            params["api_base"] = base
        if rpm:
            params["rpm"] = rpm
        fam = family or name
        self._reg(fam, FreeAPISource(
            provider=name, base_url=base or "", api_key=key,
            model=model.split("/", 1)[-1] if "/" in model else model,
            tier=tier, rpm_limit=rpm, note=note, _deployment_id=dep_id,
        ))
        return {"model_name": fam, "litellm_params": params,
                "model_info": {"id": dep_id, "tier": "free"}}

    def _build_all_deployments(self) -> List[Dict]:
        deps: List[Dict] = []

        # SiliconFlow
        sf_base = "https://api.siliconflow.cn/v1"
        for i, key in enumerate(_env_list("SILICONFLOW_KEYS")):
            if not key:
                continue
            prov = f"siliconflow_{i}"
            for m, fam, t in [
                ("Qwen/Qwen3-235B-A22B", "qwen", TIER_S),
                ("deepseek-ai/DeepSeek-V3-0324", "deepseek", TIER_S),
                ("THUDM/GLM-4-32B-0414", "glm", TIER_A),
            ]:
                deps.append(self._dep(prov, f"openai/{m}", key, sf_base, tier=t, family=fam, note="SiliconFlow free"))

        # Groq — 极速推理, 1000RPD (基于官方文档 2026.3)
        gk = _env("GROQ_API_KEY")
        if gk:
            for m, fam, t, r in [
                ("llama-3.3-70b-versatile", "llama", TIER_A, 30),       # 30RPM, 1000RPD, 12K TPM
                ("moonshotai/kimi-k2-instruct", "kimi", TIER_S, 60),    # 60RPM, 1000RPD
                ("openai/gpt-oss-120b", "gpt-oss", TIER_A, 30),        # 30RPM, 1000RPD
                ("qwen/qwen3-32b", "qwen", TIER_B, 60),                 # 60RPM, 1000RPD
                ("meta-llama/llama-4-scout-17b-16e-instruct", "llama", TIER_B, 30),
                ("llama-3.1-8b-instant", "llama", TIER_C, 30),          # 30RPM, 14400RPD
            ]:
                deps.append(self._dep("groq", f"groq/{m}", gk, rpm=r, tier=t, family=fam, note=f"Groq free {r}RPM"))

        # Cerebras — 最快推理 ~2000tok/s, 但 8K context
        ck = _env("CEREBRAS_API_KEY")
        if ck:
            for m, t in [("qwen-3-235b-a22b-instruct-2507", TIER_S), ("llama3.1-8b", TIER_C)]:
                deps.append(self._dep("cerebras", f"cerebras/{m}", ck, rpm=30, tier=t, family="qwen" if "qwen" in m else "llama", note="Cerebras 30RPM/1000RPD/8K ctx"))

        # Gemini — 2.5/3系 (2.0系已废弃, 1M上下文, RPM/RPD按模型动态)
        gk2 = _env("GEMINI_API_KEY")
        if gk2:
            gb = "https://generativelanguage.googleapis.com/v1beta/openai"
            for m, t, r in [
                ("gemini-2.5-pro", TIER_S, 5),          # 最强, RPM低但质量高, 1M ctx
                ("gemini-2.5-flash", TIER_S, 10),        # 主力, 10RPM, 1M ctx, 65K output
                ("gemini-3-flash-preview", TIER_S, 10),   # 最新preview, 1M ctx
                ("gemini-2.5-flash-lite", TIER_B, 30),    # 轻量, 30RPM, 1M ctx
                ("gemini-2.0-flash", TIER_B, 15),         # 已废弃但仍可用, 兜底
            ]:
                deps.append(self._dep("google", f"openai/{m}", gk2, gb, rpm=r, tier=t, family="gemini", note="Google AI Studio"))

        # OpenRouter — 免费模型, ~20RPM 动态限制
        ork = _env("OPENROUTER_API_KEY")
        if ork:
            for m, fam, t in [
                ("nousresearch/hermes-3-llama-3.1-405b:free", "llama", TIER_S),
                ("nvidia/nemotron-3-super-120b-a12b:free", "llama", TIER_S),
                ("minimax/minimax-m2.5:free", "minimax", TIER_S),
                ("openai/gpt-oss-120b:free", "gpt-oss", TIER_A),
                ("qwen/qwen3-coder:free", "qwen", TIER_A),
                ("qwen/qwen3-next-80b-a3b-instruct:free", "qwen", TIER_A),
                ("meta-llama/llama-3.3-70b-instruct:free", "llama", TIER_A),
                ("mistralai/mistral-small-3.1-24b-instruct:free", "mistral", TIER_B),
                ("google/gemma-3-27b-it:free", "gemma", TIER_B),
                ("stepfun/step-3.5-flash:free", "stepfun", TIER_B),
            ]:
                deps.append(self._dep("openrouter", f"openrouter/{m}", ork, rpm=20, tier=t, family=fam, note="OpenRouter free"))

        # Mistral
        mk = _env("MISTRAL_API_KEY")
        if mk:
            deps.append(self._dep("mistral", "openai/mistral-small-latest", mk, "https://api.mistral.ai/v1", rpm=1, tier=TIER_B, family="mistral"))
            deps.append(self._dep("mistral", "openai/codestral-latest", mk, "https://codestral.mistral.ai/v1", rpm=30, tier=TIER_A, family="mistral"))

        # Cohere
        cok = _env("COHERE_API_KEY")
        if cok:
            for m, t in [("command-a-reasoning-08-2025", TIER_S), ("command-a-vision-07-2025", TIER_A)]:
                deps.append(self._dep("cohere", f"cohere/{m}", cok, rpm=20, tier=t, family="cohere", note="Cohere"))

        # GitHub Models
        ght = _env("GITHUB_MODELS_TOKEN")
        if ght:
            ghb = "https://models.github.ai/inference"
            for m, fam, t in [("gpt-4.1-mini", "gpt", TIER_A), ("o4-mini", "gpt", TIER_S), ("DeepSeek-R1", "deepseek", TIER_S)]:
                deps.append(self._dep("github", f"openai/{m}", ght, ghb, rpm=15, tier=t, family=fam, note="GitHub Models"))

        # Kiro Gateway
        kk = _env("KIRO_API_KEY")
        kb = _env("KIRO_BASE_URL", "http://127.0.0.1:18793/v1")
        if kk:
            deps.append(self._dep("kiro", "openai/claude-sonnet-4", kk, kb, rpm=5, tier=TIER_S, family="claude", note="Kiro Gateway"))

        # NVIDIA NIM (信用额度制, 非真正无限, ~60RPM, 试用额度用完需购买AI Enterprise)
        nk = _env("NVIDIA_NIM_API_KEY")
        if nk:
            nvidia_base = "https://integrate.api.nvidia.com/v1"
            for m, fam, t in [
                ("meta/llama-3.3-70b-instruct", "llama", TIER_A),
                ("deepseek-ai/deepseek-r1", "deepseek", TIER_S),
                ("qwen/qwen3-235b-a22b-instruct", "qwen", TIER_S),
                ("mistralai/mixtral-8x22b-instruct-v0.1", "mistral", TIER_A),
                ("google/gemma-3-27b-it", "gemma", TIER_B),
            ]:
                deps.append(self._dep("nvidia", f"openai/{m}", nk, nvidia_base, rpm=60, tier=t, family=fam, note="NVIDIA NIM unlimited"))

        # Sambanova
        sk = _env("SAMBANOVA_API_KEY")
        if sk:
            deps.append(self._dep("sambanova", "openai/DeepSeek-R1", sk, "https://api.sambanova.ai/v1", rpm=10, tier=TIER_S, family="deepseek"))

        # iflow 无限 API（硅基流分配，14个顶级模型，无限使用）
        iflow_key = _env("SILICONFLOW_UNLIMITED_KEY")
        iflow_base = _env("SILICONFLOW_UNLIMITED_URL", "https://apis.iflow.cn/v1")
        if iflow_key:
            # 去掉 /chat/completions 后缀（LiteLLM 会自动加）
            iflow_base = iflow_base.replace("/chat/completions", "")
            for m, fam, t in [
                # instruct/非thinking版优先（速度快、有内容输出）
                ("qwen3-235b-a22b-instruct", "qwen", TIER_S),
                ("deepseek-v3.2", "deepseek", TIER_S),
                ("kimi-k2", "kimi", TIER_S),
                ("qwen3-max", "qwen", TIER_S),
                ("qwen3-coder-plus", "qwen", TIER_S),
                ("deepseek-r1", "deepseek", TIER_S),   # reasoning model
                ("deepseek-v3", "deepseek", TIER_A),
                ("qwen3-vl-plus", "qwen", TIER_A),     # vision model
                ("qwen3-32b", "qwen", TIER_A),
                ("qwen3-235b", "qwen", TIER_B),         # thinking model（慢，备用）
            ]:
                deps.append(self._dep("iflow", f"openai/{m}", iflow_key, iflow_base,
                                      rpm=500, tier=t, family=fam, note="iflow unlimited"))

        # 硅基流动付费Key池 (10条, 14元/条, 未实名, ⚠️禁止Pro模型)
        # 仅限非Pro模型: DeepSeek-R1/V3, Qwen3-235B, GLM-4-32B 等
        sf_paid_keys = _env_list("SILICONFLOW_PAID_KEYS")
        sf_paid_base = _env("SILICONFLOW_PAID_BASE_URL", "https://api.siliconflow.cn/v1")
        if sf_paid_keys:
            for i, key in enumerate(sf_paid_keys):
                prov = f"sf_paid_{i}"
                for m, fam, t in [
                    ("Qwen/Qwen3-235B-A22B", "qwen", TIER_S),          # 免费模型, 不扣余额
                    ("deepseek-ai/DeepSeek-V3-0324", "deepseek", TIER_S), # 免费模型
                    ("THUDM/GLM-4-32B-0414", "glm", TIER_A),            # 免费模型
                    ("deepseek-ai/DeepSeek-R1", "deepseek", TIER_S),     # 非Pro, 扣余额, ~175次/key
                    ("deepseek-ai/DeepSeek-V3", "deepseek", TIER_A),     # 非Pro, 扣余额, ~1000次/key
                ]:
                    deps.append(self._dep(prov, f"openai/{m}", key, sf_paid_base,
                                          tier=t, family=fam, note=f"SiliconFlow paid #{i} (no Pro!)"))

        # Volcengine 火山引擎
        vk = _env("VOLCENGINE_API_KEY")
        vb = _env("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        if vk:
            deps.append(self._dep("volcengine", "openai/doubao-pro-256k", vk, vb,
                                  rpm=10, tier=TIER_A, family="doubao", note="Volcengine"))

        # GPT_API_Free (免费: gpt-5/4o系5次/天, deepseek系30次/天, mini系200次/天)
        gpk = _env("GPT_API_FREE_KEY")
        gpb = _env("GPT_API_FREE_BASE_URL", "https://api.gpt.ge/v1")
        if gpk:
            for m, fam, t, r in [
                ("gpt-4o", "gpt", TIER_S, 2),              # 5/day
                ("gpt-4o-mini", "gpt", TIER_A, 5),           # 200/day
                ("deepseek-r1", "deepseek", TIER_S, 2),      # 30/day
                ("deepseek-v3", "deepseek", TIER_A, 2),      # 30/day
            ]:
                deps.append(self._dep("gpt_free", f"openai/{m}", gpk, gpb, rpm=r, tier=t, family=fam, note="GPT_API_Free"))

        # g4f 兜底
        g4f_base = _env("G4F_BASE_URL", "http://127.0.0.1:18891/v1")
        deps.append(self._dep("g4f", "openai/auto", "dummy", g4f_base, tier=TIER_A, family="g4f", note="g4f fallback"))

        return deps

    # ---- 初始化 ----

    def initialize(self):
        """构建 deployments 并初始化 LiteLLM Router"""
        deps = self._build_all_deployments()
        if not deps:
            logger.warning("[LiteLLMPool] 无可用 deployment")
            return

        families = list({d["model_name"] for d in deps})
        fallbacks = [{f: ["g4f"]} for f in families if f != "g4f"]

        try:
            self._router = Router(
                model_list=deps,
                fallbacks=fallbacks,
                num_retries=2,
                timeout=30,
                allowed_fails=3,
                cooldown_time=30,
                retry_after=5,
                routing_strategy="simple-shuffle",
                set_verbose=False,
            )
            logger.info(f"[LiteLLMPool] Router OK: {len(deps)} deployments, {len(families)} groups")
        except Exception as e:
            logger.error(f"[LiteLLMPool] Router init failed: {e}")
            self._router = None

    # ---- 核心调用 ----

    async def acompletion(
        self,
        model_family: Optional[str],
        messages: List[Dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        cache_ttl: int = 3600,
        no_cache: bool = False,
        **kwargs,
    ):
        """统一 LLM 调用入口，替代 api_mixin 中所有手写 HTTP 调用

        Args:
            cache_ttl: Cache TTL in seconds (default 3600). 0 disables cache.
            no_cache: Force bypass cache for this request.
        """
        if not self._router:
            raise RuntimeError("LiteLLMPool 未初始化")

        model = model_family or self._pick_strongest_family()
        all_msgs = ([{"role": "system", "content": system_prompt}] + messages) if system_prompt else messages

        # ---- Cache layer (non-streaming only) ----
        use_cache = (
            not stream
            and not no_cache
            and cache_ttl > 0
            and _HAS_LLM_CACHE
        )

        if use_cache:
            cache_key = _make_cache_key(all_msgs, model, temperature)
            try:
                cached = _llm_cache_get(cache_key)
                if cached is not None:
                    logger.debug(f"[LiteLLMPool] cache HIT key={cache_key[:16]}… model={model}")
                    return cached
            except Exception:
                logger.debug("Silenced exception", exc_info=True)  # Cache read error → fall through to LLM

        start = time.time()
        try:
            response = await self._router.acompletion(
                model=model, messages=all_msgs,
                temperature=temperature, max_tokens=max_tokens,
                stream=stream, **kwargs,
            )
            latency = (time.time() - start) * 1000
            self._call_count += 1
            self._total_latency += latency
            if hasattr(response, "usage") and response.usage:
                self._total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
                self._total_output_tokens += getattr(response.usage, "completion_tokens", 0)
                # Calculate cost from LiteLLM response
                try:
                    cost = litellm.completion_cost(completion_response=response)
                    self._total_cost += cost
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)  # Free models have no cost data

            # ---- Store to cache ----
            if use_cache:
                try:
                    _llm_cache_set(cache_key, response, cache_ttl)
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)  # Cache write error → ignore

            return response
        except Exception as e:
            self._error_count += 1
            logger.error(f"[LiteLLMPool] acompletion failed (model={model}): {e}")
            raise

    def _pick_strongest_family(self) -> str:
        best_fam, best_score = "g4f", 0
        for fam, sources in self._sources.items():
            for src in sources:
                if src.can_accept_request():
                    score = get_model_score(src.model)
                    if score > best_score:
                        best_score = score
                        best_fam = fam
        return best_fam

    # ---- 兼容旧接口 ----

    def get_best_source(self, model_family: str, min_tier: str = TIER_C,
                        routing: Optional[str] = None) -> Optional[FreeAPISource]:
        min_val = _TIER_ORDER.get(min_tier, 3)
        avail = [s for s in self._sources.get(model_family, [])
                 if s.can_accept_request() and _TIER_ORDER.get(s.tier, 9) <= min_val]
        if not avail:
            return None
        avail.sort(key=lambda s: -get_model_score(s.model))
        return avail[0]

    def get_any_source(self, min_tier: str = TIER_C,
                       routing: Optional[str] = None) -> Optional[Tuple[str, FreeAPISource]]:
        min_val = _TIER_ORDER.get(min_tier, 3)
        best, best_score, best_fam = None, -1, ""
        for fam, sources in self._sources.items():
            for s in sources:
                if s.can_accept_request() and _TIER_ORDER.get(s.tier, 9) <= min_val:
                    score = get_model_score(s.model)
                    if score > best_score:
                        best, best_score, best_fam = s, score, fam
        return (best_fam, best) if best else None

    # DEPRECATED: record_success/record_error are dead code — LiteLLM Router
    # handles success/error tracking internally. Kept for backward compatibility.
    def record_success(self, source: FreeAPISource, latency_ms: float = 0,
                       input_tokens: int = 0, output_tokens: int = 0):
        source.used_today += 1
        source.last_used = time.time()
        source.consecutive_errors = 0

    def record_error(self, source: FreeAPISource, error: str = ""):
        source.consecutive_errors += 1

    def add_source(self, model_family: str, source: FreeAPISource):
        self._reg(model_family, source)

    def acquire_request(self, source: FreeAPISource):
        pass  # LiteLLM handles concurrency

    def release_request(self, source: FreeAPISource):
        pass

    def reset_daily_counters(self):
        for sources in self._sources.values():
            for src in sources:
                src.used_today = 0
                src.consecutive_errors = 0
                src.disabled = False

    def remove_exhausted(self):
        return 0  # LiteLLM handles cooldown

    def get_stats(self) -> Dict:
        total = sum(len(v) for v in self._sources.values())
        active = sum(1 for v in self._sources.values() for s in v if s.can_accept_request())
        avg_lat = self._total_latency / max(self._call_count, 1)
        return {
            "total_sources": total, "active_sources": active,
            "model_families": len(self._sources),
            "routing_strategy": "litellm-router",
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "total_cost_usd": round(self._total_cost, 6),
            "avg_latency_ms": round(avg_lat, 1),
            "total_calls": self._call_count, "total_errors": self._error_count,
            "success_rate": round((self._call_count - self._error_count) / max(self._call_count, 1), 3),
            "families": {
                k: {"total": len(v), "active": sum(1 for s in v if s.can_accept_request()),
                     "total_requests": sum(s.used_today for s in v)}
                for k, v in self._sources.items()
            },
            "by_provider": self._stats_by_provider(),
            "engine": "litellm",
        }

    def _stats_by_provider(self) -> Dict:
        provs: Dict[str, Dict] = {}
        for sources in self._sources.values():
            for s in sources:
                p = s.provider
                if p not in provs:
                    provs[p] = {"models": 0, "active": 0, "requests_today": 0, "errors": 0}
                provs[p]["models"] += 1
                provs[p]["active"] += 1 if s.can_accept_request() else 0
                provs[p]["requests_today"] += s.used_today
                provs[p]["errors"] += s.consecutive_errors
        return provs

    def save_state(self):
        pass  # LiteLLM manages state

    def load_state(self):
        pass

    async def health_check(self, timeout: float = 10.0) -> Dict:
        """启动时健康检查 — 快速 ping 每个 provider，禁用不可用的。

        Returns:
            {"checked": N, "healthy": N, "disabled": [...], "elapsed_s": float}
        """
        import asyncio
        start = time.time()
        checked = 0
        healthy = 0
        disabled_providers = []

        # Group sources by provider to avoid redundant checks
        providers_seen: Dict[str, bool] = {}

        for family, sources in self._sources.items():
            for src in sources:
                if src.provider in providers_seen:
                    # Apply same result
                    if not providers_seen[src.provider]:
                        src.disabled = True
                    continue

                checked += 1
                try:
                    # Minimal ping: 1-token completion with short timeout
                    resp = await asyncio.wait_for(
                        self.acompletion(
                            model_family=family,
                            messages=[{"role": "user", "content": "hi"}],
                            max_tokens=1,
                            temperature=0,
                        ),
                        timeout=timeout,
                    )
                    providers_seen[src.provider] = True
                    healthy += 1
                except Exception as e:
                    logger.warning(f"[健康检查] {src.provider}/{src.model} 不可用: {e}")
                    providers_seen[src.provider] = False
                    src.disabled = True
                    disabled_providers.append(f"{src.provider}/{src.model}")

        # Mark all sources of failed providers as disabled
        for family, sources in self._sources.items():
            for src in sources:
                if src.provider in providers_seen and not providers_seen[src.provider]:
                    src.disabled = True

        elapsed = time.time() - start
        result = {
            "checked": checked,
            "healthy": healthy,
            "disabled": disabled_providers,
            "elapsed_s": round(elapsed, 2),
        }
        logger.info(f"[健康检查] {healthy}/{checked} providers 可用, "
                     f"禁用 {len(disabled_providers)} 个, 耗时 {elapsed:.1f}s")
        return result


# ============================================================
# 全局单例 + 初始化
# ============================================================

free_pool = LiteLLMPool()


def init_free_pool():
    free_pool.initialize()
    stats = free_pool.get_stats()
    logger.info(f"[LiteLLMPool] {stats['total_sources']} sources, {stats['active_sources']} active, engine=litellm")


def init_adaptive_router():
    """兼容旧接口 — LiteLLM Router 内置自适应路由"""
    logger.info("[LiteLLMPool] adaptive routing handled by LiteLLM Router")


adaptive_router = None  # 兼容旧 import
