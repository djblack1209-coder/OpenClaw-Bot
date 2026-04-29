"""
LLM 路由配置模块的单元测试

覆盖范围:
  - load_routing_config: JSON 加载、文件缺失、格式错误
  - build_deployments_from_config: 从配置构建 deployment 列表
  - build_fallbacks_from_config: 降级链构建
  - get_bot_model_family: Bot→family 映射
  - get_router_config: Router 全局参数
  - _resolve_keys / _resolve_base_url: 内部解析逻辑
"""

import json
import os
import pytest
from unittest.mock import patch

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_routing_config import (
    load_routing_config,
    build_deployments_from_config,
    build_fallbacks_from_config,
    get_bot_model_family,
    get_router_config,
    _resolve_keys,
    _resolve_base_url,
    _env,
    _env_list,
)


# ============ 测试用的最小配置 ============


def _minimal_config() -> dict:
    """返回最小合法配置字典，用于各测试复用"""
    return {
        "providers": {
            "test_provider": {
                "env_key": "TEST_API_KEY",
                "prefix": "openai/",
                "timeout": 10,
                "stream_timeout": 20,
                "note": "测试用 provider",
                "models": [
                    {"id": "model-a", "family": "alpha", "tier": "S", "rpm": 60},
                    {"id": "model-b", "family": "beta", "tier": "B"},
                ],
            }
        },
        "fallback_chains": {
            "default": ["alpha", "beta", "g4f"],
            "alpha": ["beta", "g4f"],
        },
        "bot_model_family": {
            "bot_one": "alpha",
            "bot_two": "beta",
            "bot_free": None,
        },
        "router_config": {
            "num_retries": 2,
            "timeout": 10,
            "stream_timeout": 20,
            "allowed_fails": 2,
            "cooldown_time": 15,
            "retry_after": 3,
            "routing_strategy": "simple-shuffle",
        },
    }


def _write_config(tmp_path, data: dict) -> str:
    """把配置写入临时 JSON 文件，返回路径字符串"""
    path = tmp_path / "llm_routing.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ============ load_routing_config 测试 ============


class TestLoadRoutingConfig:
    """load_routing_config 函数的测试"""

    def test_从合法json加载配置(self, tmp_path):
        """合法 JSON 文件应正确加载为字典"""
        config_data = _minimal_config()
        path = _write_config(tmp_path, config_data)

        result = load_routing_config(path)

        assert isinstance(result, dict)
        assert "providers" in result
        assert "test_provider" in result["providers"]

    def test_文件不存在返回空字典(self, tmp_path):
        """配置文件不存在时返回空字典，不抛异常"""
        fake_path = str(tmp_path / "nonexistent.json")

        result = load_routing_config(fake_path)

        assert result == {}

    def test_畸形json返回空字典(self, tmp_path):
        """JSON 格式错误时返回空字典，不抛异常"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{这不是合法JSON", encoding="utf-8")

        result = load_routing_config(str(bad_file))

        assert result == {}

    def test_空json文件返回空对象(self, tmp_path):
        """空 JSON 对象 {} 应正确加载"""
        path = _write_config(tmp_path, {})

        result = load_routing_config(path)

        assert result == {}

    def test_默认路径参数为None时使用内置路径(self):
        """config_path=None 时应使用模块内置的 _CONFIG_PATH"""
        # 不传路径，验证不抛异常（文件可能存在也可能不存在）
        result = load_routing_config(None)
        assert isinstance(result, dict)

    def test_unicode内容正确加载(self, tmp_path):
        """包含中文的 JSON 应正确加载"""
        data = {"providers": {}, "_meta": {"note": "中文测试说明"}}
        path = _write_config(tmp_path, data)

        result = load_routing_config(path)

        assert result["_meta"]["note"] == "中文测试说明"

    def test_providers字段缺失不报错(self, tmp_path):
        """只有 router_config 没有 providers 的配置应正常加载"""
        data = {"router_config": {"num_retries": 1}}
        path = _write_config(tmp_path, data)

        result = load_routing_config(path)

        assert "router_config" in result
        assert "providers" not in result


# ============ _resolve_keys 测试 ============


class TestResolveKeys:
    """API Key 解析逻辑测试"""

    def test_单key环境变量(self):
        """env_key 指定的单个 key 应正确读取"""
        cfg = {"env_key": "TEST_SINGLE_KEY"}
        with patch.dict(os.environ, {"TEST_SINGLE_KEY": "sk-abc123"}):
            keys = _resolve_keys(cfg)
        assert keys == ["sk-abc123"]

    def test_多key环境变量(self):
        """multi_key=true 时从逗号分隔的环境变量读取多个 key"""
        cfg = {"env_key": "TEST_MULTI_KEYS", "multi_key": True}
        with patch.dict(os.environ, {"TEST_MULTI_KEYS": "key1,key2,key3"}):
            keys = _resolve_keys(cfg)
        assert keys == ["key1", "key2", "key3"]

    def test_多key有空格自动清理(self):
        """逗号分隔的 key 带空格时应自动 strip"""
        cfg = {"env_key": "TEST_SPACED_KEYS", "multi_key": True}
        with patch.dict(os.environ, {"TEST_SPACED_KEYS": " key1 , key2 , key3 "}):
            keys = _resolve_keys(cfg)
        assert keys == ["key1", "key2", "key3"]

    def test_环境变量为空返回空列表(self):
        """env_key 对应的环境变量为空字符串时返回空列表"""
        cfg = {"env_key": "TEST_EMPTY_KEY"}
        with patch.dict(os.environ, {"TEST_EMPTY_KEY": ""}, clear=False):
            keys = _resolve_keys(cfg)
        assert keys == []

    def test_环境变量不存在返回空列表(self):
        """env_key 对应的环境变量完全不存在时返回空列表"""
        cfg = {"env_key": "ABSENT_ENV_VAR_FOR_TEST"}
        # 确保这个变量不存在
        env_copy = os.environ.copy()
        env_copy.pop("ABSENT_ENV_VAR_FOR_TEST", None)
        with patch.dict(os.environ, env_copy, clear=True):
            keys = _resolve_keys(cfg)
        assert keys == []

    def test_optional_key有值(self):
        """env_key_optional 有值时使用该值"""
        cfg = {"env_key_optional": "OPT_KEY"}
        with patch.dict(os.environ, {"OPT_KEY": "sk-opt"}):
            keys = _resolve_keys(cfg)
        assert keys == ["sk-opt"]

    def test_optional_key为空返回dummy(self):
        """env_key_optional 为空时返回 dummy（用于 g4f 等无 key 服务）"""
        cfg = {"env_key_optional": "OPT_KEY_EMPTY"}
        with patch.dict(os.environ, {"OPT_KEY_EMPTY": ""}, clear=False):
            keys = _resolve_keys(cfg)
        assert keys == ["dummy"]

    def test_无key但有base_url返回dummy(self):
        """没有 env_key 但有 base_url_default 时返回 dummy（本地服务）"""
        cfg = {"base_url_default": "http://localhost:1337/v1"}
        keys = _resolve_keys(cfg)
        assert keys == ["dummy"]

    def test_无key也无url返回空(self):
        """既没有 key 也没有 url 时返回空列表"""
        cfg = {}
        keys = _resolve_keys(cfg)
        assert keys == []

    def test_env_key优先于optional(self):
        """env_key 有值时应优先使用，不走 optional 分支"""
        cfg = {"env_key": "PRIMARY_KEY", "env_key_optional": "OPT_KEY"}
        with patch.dict(os.environ, {"PRIMARY_KEY": "sk-primary", "OPT_KEY": "sk-opt"}):
            keys = _resolve_keys(cfg)
        assert keys == ["sk-primary"]


# ============ _resolve_base_url 测试 ============


class TestResolveBaseUrl:
    """base_url 解析逻辑测试"""

    def test_环境变量覆盖优先(self):
        """base_url_env 指定的环境变量应优先于配置文件的 base_url"""
        cfg = {
            "base_url_env": "CUSTOM_BASE_URL",
            "base_url": "https://default.api.com/v1",
        }
        with patch.dict(os.environ, {"CUSTOM_BASE_URL": "https://custom.api.com/v1"}):
            url = _resolve_base_url(cfg)
        assert url == "https://custom.api.com/v1"

    def test_环境变量为空回退到base_url(self):
        """base_url_env 为空时回退到 base_url 字段"""
        cfg = {
            "base_url_env": "EMPTY_BASE_URL",
            "base_url": "https://fallback.api.com/v1",
        }
        with patch.dict(os.environ, {"EMPTY_BASE_URL": ""}, clear=False):
            url = _resolve_base_url(cfg)
        assert url == "https://fallback.api.com/v1"

    def test_base_url固定值(self):
        """没有 base_url_env 时使用 base_url 字段"""
        cfg = {"base_url": "https://api.siliconflow.cn/v1"}
        url = _resolve_base_url(cfg)
        assert url == "https://api.siliconflow.cn/v1"

    def test_回退到默认值(self):
        """没有 env 和 base_url 时使用 base_url_default"""
        cfg = {"base_url_default": "http://localhost:1337/v1"}
        url = _resolve_base_url(cfg)
        assert url == "http://localhost:1337/v1"

    def test_全部为空返回空字符串(self):
        """所有 url 字段都没有时返回空字符串"""
        cfg = {}
        url = _resolve_base_url(cfg)
        assert url == ""


# ============ build_deployments_from_config 测试 ============


class TestBuildDeployments:
    """从配置构建 deployment 列表的测试"""

    @staticmethod
    def _fake_dep(prov, model, key, **kwargs):
        """模拟 LiteLLMPool._dep 方法，原样返回参数字典"""
        return {
            "provider": prov,
            "model": model,
            "api_key": key,
            **kwargs,
        }

    def test_单provider多model生成正确数量(self):
        """1 个 provider、2 个 model、1 个 key → 2 个 deployment"""
        config = _minimal_config()
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        assert len(deps) == 2

    def test_deployment包含正确的model前缀(self):
        """model id 应拼接 prefix"""
        config = _minimal_config()
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        model_names = [d["model"] for d in deps]
        assert "openai/model-a" in model_names
        assert "openai/model-b" in model_names

    def test_deployment包含正确的tier和family(self):
        """tier 和 family 应从 model 配置传递"""
        config = _minimal_config()
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        dep_a = next(d for d in deps if d["model"] == "openai/model-a")
        assert dep_a["tier"] == "S"
        assert dep_a["family"] == "alpha"

    def test_多key产生多组deployment(self):
        """multi_key=true 且有 3 个 key → 每个 model 产生 3 个 deployment"""
        config = {
            "providers": {
                "multi": {
                    "env_key": "MULTI_KEYS",
                    "multi_key": True,
                    "prefix": "",
                    "models": [
                        {"id": "m1", "family": "f1", "tier": "A"},
                    ],
                }
            }
        }
        with patch.dict(os.environ, {"MULTI_KEYS": "k1,k2,k3"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        # 3 个 key × 1 个 model = 3 个 deployment
        assert len(deps) == 3

    def test_多key的provider_id有后缀(self):
        """多 key 时 provider_id 应带下标后缀（如 multi_0, multi_1）"""
        config = {
            "providers": {
                "multi": {
                    "env_key": "MULTI_KEYS_2",
                    "multi_key": True,
                    "prefix": "",
                    "models": [
                        {"id": "m1", "family": "f1", "tier": "A"},
                    ],
                }
            }
        }
        with patch.dict(os.environ, {"MULTI_KEYS_2": "k1,k2"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        providers = [d["provider"] for d in deps]
        assert "multi_0" in providers
        assert "multi_1" in providers

    def test_无key的provider被跳过(self):
        """env_key 对应环境变量不存在时，该 provider 整体跳过"""
        config = _minimal_config()
        # 不设置 TEST_API_KEY 环境变量
        env_copy = os.environ.copy()
        env_copy.pop("TEST_API_KEY", None)
        with patch.dict(os.environ, env_copy, clear=True):
            deps = build_deployments_from_config(config, self._fake_dep)
        assert len(deps) == 0

    def test_空providers返回空列表(self):
        """providers 为空时返回空列表"""
        config = {"providers": {}}
        deps = build_deployments_from_config(config, self._fake_dep)
        assert deps == []

    def test_无providers字段返回空列表(self):
        """配置中没有 providers 字段时返回空列表"""
        config = {}
        deps = build_deployments_from_config(config, self._fake_dep)
        assert deps == []

    def test_timeout和stream_timeout传递正确(self):
        """provider 级别的 timeout 配置应传递到每个 deployment"""
        config = _minimal_config()
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        for dep in deps:
            assert dep["timeout"] == 10
            assert dep["stream_timeout"] == 20

    def test_rpm默认值为0(self):
        """model 没有指定 rpm 时默认为 0"""
        config = _minimal_config()
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        dep_b = next(d for d in deps if d["model"] == "openai/model-b")
        assert dep_b["rpm"] == 0

    def test_base_url传递到deployment(self):
        """provider 的 base_url 应传递到每个 deployment"""
        config = {
            "providers": {
                "local": {
                    "env_key_optional": "G4F_KEY",
                    "base_url_default": "http://localhost:1337/v1",
                    "prefix": "openai/",
                    "models": [
                        {"id": "auto", "family": "g4f", "tier": "C"},
                    ],
                }
            }
        }
        deps = build_deployments_from_config(config, self._fake_dep)
        assert len(deps) == 1
        assert deps[0]["base"] == "http://localhost:1337/v1"


# ============ build_fallbacks_from_config 测试 ============


class TestBuildFallbacks:
    """降级链构建测试"""

    def test_使用专属降级链(self):
        """family 有专属降级链时应优先使用"""
        config = _minimal_config()
        active = {"alpha", "beta", "g4f"}

        fallbacks = build_fallbacks_from_config(config, active)

        # alpha 有专属链 ["beta", "g4f"]
        alpha_fb = next(f for f in fallbacks if "alpha" in f)
        assert alpha_fb["alpha"] == ["beta", "g4f"]

    def test_使用默认降级链(self):
        """family 没有专属链时应使用 default"""
        config = _minimal_config()
        active = {"alpha", "beta", "g4f"}

        fallbacks = build_fallbacks_from_config(config, active)

        # beta 没有专属链，用 default=["alpha","beta","g4f"]，去掉自身 beta
        beta_fb = next(f for f in fallbacks if "beta" in f)
        assert "beta" not in beta_fb["beta"]
        assert "alpha" in beta_fb["beta"]

    def test_g4f不生成降级链(self):
        """g4f 是终极兜底，自身不应该有降级链"""
        config = _minimal_config()
        active = {"alpha", "beta", "g4f"}

        fallbacks = build_fallbacks_from_config(config, active)

        # 不应有 g4f 为 key 的条目
        g4f_entries = [f for f in fallbacks if "g4f" in f]
        assert len(g4f_entries) == 0

    def test_不活跃的family被过滤(self):
        """降级链中不活跃的 family 应被过滤掉"""
        config = {
            "fallback_chains": {
                "default": ["alpha", "beta", "gamma", "g4f"],
            }
        }
        active = {"alpha", "gamma"}  # beta 和 g4f 不活跃

        fallbacks = build_fallbacks_from_config(config, active)

        alpha_fb = next(f for f in fallbacks if "alpha" in f)
        assert "beta" not in alpha_fb["alpha"]
        assert "gamma" in alpha_fb["alpha"]

    def test_空active集合返回空列表(self):
        """没有活跃 family 时返回空列表"""
        config = _minimal_config()

        fallbacks = build_fallbacks_from_config(config, set())

        assert fallbacks == []

    def test_只有g4f活跃返回空列表(self):
        """只有 g4f 活跃时返回空列表（g4f 自身不生成链）"""
        config = _minimal_config()

        fallbacks = build_fallbacks_from_config(config, {"g4f"})

        assert fallbacks == []

    def test_降级链去掉自身(self):
        """降级链中不应包含 family 自身"""
        config = {
            "fallback_chains": {
                "default": ["alpha", "beta", "g4f"],
            }
        }
        active = {"alpha", "beta", "g4f"}

        fallbacks = build_fallbacks_from_config(config, active)

        for fb in fallbacks:
            for family, chain in fb.items():
                assert family not in chain, f"{family} 的降级链不应包含自身"

    def test_无fallback_chains字段使用硬编码默认值(self):
        """配置中没有 fallback_chains 时使用代码内的硬编码默认值"""
        config = {}
        active = {"qwen", "deepseek", "g4f"}

        fallbacks = build_fallbacks_from_config(config, active)

        # 默认链是 ["qwen","deepseek","g4f"]
        qwen_fb = next(f for f in fallbacks if "qwen" in f)
        assert "deepseek" in qwen_fb["qwen"]
        assert "g4f" in qwen_fb["qwen"]


# ============ get_bot_model_family 测试 ============


class TestGetBotModelFamily:
    """Bot→model_family 映射测试"""

    def test_已知bot返回正确family(self):
        """已配置的 bot_id 应返回对应 family"""
        config = _minimal_config()
        assert get_bot_model_family(config, "bot_one") == "alpha"
        assert get_bot_model_family(config, "bot_two") == "beta"

    def test_未知bot返回None(self):
        """未配置的 bot_id 应返回 None"""
        config = _minimal_config()
        assert get_bot_model_family(config, "unknown_bot") is None

    def test_bot映射为null返回None(self):
        """bot_model_family 中值为 null 的 bot 应返回 None"""
        config = _minimal_config()
        assert get_bot_model_family(config, "bot_free") is None

    def test_无bot_model_family字段返回None(self):
        """配置中没有 bot_model_family 字段时返回 None"""
        config = {}
        assert get_bot_model_family(config, "any_bot") is None


# ============ get_router_config 测试 ============


class TestGetRouterConfig:
    """Router 全局配置参数测试"""

    def test_返回配置中的router_config(self):
        """有 router_config 字段时应原样返回"""
        config = _minimal_config()
        rc = get_router_config(config)
        assert rc["num_retries"] == 2
        assert rc["routing_strategy"] == "simple-shuffle"

    def test_无router_config返回默认值(self):
        """没有 router_config 字段时应返回硬编码默认值"""
        config = {}
        rc = get_router_config(config)
        assert rc["num_retries"] == 3
        assert rc["timeout"] == 15
        assert rc["routing_strategy"] == "simple-shuffle"

    def test_默认值包含所有必要字段(self):
        """默认返回值应包含所有必要的 Router 配置字段"""
        config = {}
        rc = get_router_config(config)
        expected_keys = {
            "num_retries",
            "timeout",
            "stream_timeout",
            "allowed_fails",
            "cooldown_time",
            "retry_after",
            "routing_strategy",
        }
        assert set(rc.keys()) == expected_keys


# ============ _env / _env_list 辅助函数测试 ============


class TestEnvHelpers:
    """环境变量辅助函数测试"""

    def test_env读取已设置变量(self):
        """_env 应正确读取已设置的环境变量"""
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            assert _env("MY_VAR") == "hello"

    def test_env未设置返回空字符串(self):
        """_env 对不存在的变量应返回空字符串"""
        env_copy = os.environ.copy()
        env_copy.pop("NONEXISTENT_VAR_XYZ", None)
        with patch.dict(os.environ, env_copy, clear=True):
            assert _env("NONEXISTENT_VAR_XYZ") == ""

    def test_env_list正常分割(self):
        """_env_list 应按逗号分割并 strip"""
        with patch.dict(os.environ, {"LIST_VAR": "a, b, c"}):
            assert _env_list("LIST_VAR") == ["a", "b", "c"]

    def test_env_list空值返回空列表(self):
        """_env_list 空字符串应返回空列表"""
        with patch.dict(os.environ, {"EMPTY_LIST": ""}):
            assert _env_list("EMPTY_LIST") == []

    def test_env_list不存在返回空列表(self):
        """_env_list 变量不存在应返回空列表"""
        env_copy = os.environ.copy()
        env_copy.pop("NO_SUCH_LIST_VAR", None)
        with patch.dict(os.environ, env_copy, clear=True):
            assert _env_list("NO_SUCH_LIST_VAR") == []

    def test_env_list过滤空项(self):
        """_env_list 应过滤掉空项（如连续逗号）"""
        with patch.dict(os.environ, {"SPARSE_LIST": "a,,b, ,c"}):
            result = _env_list("SPARSE_LIST")
            assert result == ["a", "b", "c"]


# ============ 集成测试：从文件到 deployment 完整链路 ============


class TestEndToEnd:
    """端到端集成测试：从 JSON 文件加载到构建 deployment"""

    @staticmethod
    def _fake_dep(prov, model, key, **kwargs):
        return {"provider": prov, "model": model, "api_key": key, **kwargs}

    def test_完整链路_加载配置并构建deployment(self, tmp_path):
        """从 JSON 加载 → 构建 deployment → 构建 fallback 完整流程"""
        config_data = _minimal_config()
        path = _write_config(tmp_path, config_data)

        # 加载配置
        config = load_routing_config(path)
        assert config != {}

        # 构建 deployment
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-e2e"}):
            deps = build_deployments_from_config(config, self._fake_dep)
        assert len(deps) == 2

        # 从 deployment 提取活跃 family 集合
        active = {d["family"] for d in deps}
        active.add("g4f")  # g4f 通常作为兜底总是活跃

        # 构建 fallback 链
        fallbacks = build_fallbacks_from_config(config, active)
        assert len(fallbacks) > 0

    def test_配置文件损坏时整个流程安全降级(self, tmp_path):
        """配置文件损坏时所有后续操作应安全返回空值"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON", encoding="utf-8")

        config = load_routing_config(str(bad_file))
        assert config == {}

        deps = build_deployments_from_config(config, self._fake_dep)
        assert deps == []

        fallbacks = build_fallbacks_from_config(config, set())
        assert fallbacks == []

        family = get_bot_model_family(config, "any")
        assert family is None

        rc = get_router_config(config)
        assert rc["num_retries"] == 3  # 默认值
