"""
LLM 路由配置加载器

从 config/llm_routing.json 加载所有 provider/模型/降级链配置。
借鉴 Portkey AI Gateway 的 JSON Config 驱动模式。

设计原则:
  - 修改 JSON 即可调整路由规则，无需改代码
  - 保持与现有 _dep() / _build_all_deployments() 的接口兼容
  - 支持多 key 轮转、环境变量引用、可选依赖
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 配置文件路径
_CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm_routing.json"


def _env(name: str) -> str:
    """读取环境变量"""
    return os.getenv(name, "")


def _env_list(name: str) -> List[str]:
    """读取逗号分隔的环境变量列表"""
    val = os.getenv(name, "")
    if not val:
        return []
    return [k.strip() for k in val.split(",") if k.strip()]


def load_routing_config(config_path: Optional[str] = None) -> Dict:
    """
    加载路由配置 JSON

    参数:
        config_path: 自定义配置文件路径（测试用）

    返回:
        配置字典。文件不存在或解析失败时返回空字典
    """
    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        logger.warning(f"[RoutingConfig] 配置文件不存在: {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"[RoutingConfig] 加载成功: {len(config.get('providers', {}))} 个 provider")
        return config
    except Exception as e:
        logger.error(f"[RoutingConfig] 配置文件解析失败: {e}")
        return {}


def build_deployments_from_config(
    config: Dict,
    dep_fn,
) -> List[Dict]:
    """
    从 JSON 配置构建 LiteLLM deployment 列表

    参数:
        config: load_routing_config() 返回的字典
        dep_fn: LiteLLMPool._dep 方法引用（用于构建 deployment dict）

    返回:
        LiteLLM deployment 列表 (同 _build_all_deployments 返回格式)
    """
    providers = config.get("providers", {})
    deps: List[Dict] = []

    for provider_name, provider_cfg in providers.items():
        # 解析 API Key
        keys = _resolve_keys(provider_cfg)
        if not keys:
            continue

        # 解析 base_url
        base_url = _resolve_base_url(provider_cfg)

        # 通用参数
        prefix = provider_cfg.get("prefix", "")
        timeout = provider_cfg.get("timeout", 15)
        stream_timeout = provider_cfg.get("stream_timeout", 30)
        note = provider_cfg.get("note", provider_name)

        # 为每个 key 和 model 组合生成 deployment
        for key_idx, api_key in enumerate(keys):
            prov_id = f"{provider_name}_{key_idx}" if len(keys) > 1 else provider_name

            for model_cfg in provider_cfg.get("models", []):
                model_id = model_cfg["id"]
                family = model_cfg.get("family", "unknown")
                tier = model_cfg.get("tier", "B")
                rpm = model_cfg.get("rpm", 0)

                # 构建 deployment（调用 LiteLLMPool._dep）
                dep = dep_fn(
                    prov_id,
                    f"{prefix}{model_id}",
                    api_key,
                    base_url=base_url,
                    tier=tier,
                    family=family,
                    note=note,
                    timeout=timeout,
                    stream_timeout=stream_timeout,
                    rpm=rpm,
                )
                deps.append(dep)

    logger.info(f"[RoutingConfig] 构建了 {len(deps)} 个 deployment")
    return deps


def build_fallbacks_from_config(
    config: Dict,
    active_families: set,
) -> List[Dict]:
    """
    从 JSON 配置构建 LiteLLM fallback 链

    参数:
        config: 路由配置字典
        active_families: 当前实际注册的 family 集合

    返回:
        LiteLLM fallback 列表 (格式: [{"family_a": ["family_b", "g4f"]}, ...])
    """
    fallback_cfg = config.get("fallback_chains", {})
    default_chain = fallback_cfg.get("default", ["qwen", "deepseek", "g4f"])
    fallbacks = []

    for family in active_families:
        if family == "g4f":
            continue  # g4f 是终极兜底

        # 优先用该 family 的专属降级链，否则用 default
        chain_template = fallback_cfg.get(family, default_chain)

        # 过滤掉不活跃的 family 和自身
        chain = [f for f in chain_template if f in active_families and f != family]
        if chain:
            fallbacks.append({family: chain})

    return fallbacks


def get_bot_model_family(config: Dict, bot_id: str) -> Optional[str]:
    """从配置获取 Bot 对应的 model_family"""
    mapping = config.get("bot_model_family", {})
    return mapping.get(bot_id)


def get_router_config(config: Dict) -> Dict:
    """获取 Router 全局配置参数"""
    return config.get(
        "router_config",
        {
            "num_retries": 3,
            "timeout": 15,
            "stream_timeout": 30,
            "allowed_fails": 3,
            "cooldown_time": 30,
            "retry_after": 5,
            "routing_strategy": "simple-shuffle",
        },
    )


def _resolve_keys(provider_cfg: Dict) -> List[str]:
    """解析 provider 的 API Key（支持单 key 和多 key）"""
    # 必选 key
    env_key = provider_cfg.get("env_key", "")
    if env_key:
        if provider_cfg.get("multi_key"):
            keys = _env_list(env_key)
        else:
            k = _env(env_key)
            keys = [k] if k else []
        if keys:
            return keys

    # 可选 key（如 g4f 可以无 key）
    env_key_optional = provider_cfg.get("env_key_optional", "")
    if env_key_optional:
        k = _env(env_key_optional)
        return [k] if k else ["dummy"]  # g4f 等本地服务不需要真 key

    # 无 key 但有 base_url（本地服务）
    if provider_cfg.get("base_url_default") or provider_cfg.get("base_url"):
        return ["dummy"]

    return []


def _resolve_base_url(provider_cfg: Dict) -> str:
    """解析 provider 的 base_url（支持环境变量覆盖和默认值）"""
    # 优先从环境变量读取
    env_name = provider_cfg.get("base_url_env", "")
    if env_name:
        url = _env(env_name)
        if url:
            return url

    # 其次用配置中的固定值
    url = provider_cfg.get("base_url", "")
    if url:
        return url

    # 最后用默认值
    return provider_cfg.get("base_url_default", "")
