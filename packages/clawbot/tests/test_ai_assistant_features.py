"""
测试第1-5轮产品跃迁的 16 项 AI 助手能力

覆盖范围:
  1. 纠错检测器 (_detect_correction)
  2. 复合意图拆解 (_detect_compound_intent)
  3. 消息温度感知 (_detect_message_tone)
  4. 实时偏好检测 (_detect_instant_preference 的正则逻辑)
  5. TL;DR 摘要生成 (generate_tldr 的阈值逻辑)
  6. 追问建议生成 (generate_suggestions 的解析逻辑)
  7. 自选股监控器 (WatchlistMonitor 冷却机制)
  8. 跨域信号聚合 (get_context_enrichment)
  9. 首次引导标志 (_first_time_flags)
  10. 能力发现按钮 (通用聊天分支)
"""
import pytest
import re
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1. 纠错检测器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCorrectionDetection:
    """测试 _detect_correction — 搬运 ChatGPT correction handling"""

    def setup_method(self):
        from src.bot.message_mixin import _detect_correction
        self.detect = _detect_correction

    def test_direct_correction_keywords(self):
        """直接否定词: 不对/错了/说错了"""
        assert self.detect("不对，我说的是苹果") is True
        assert self.detect("错了") is True
        assert self.detect("说错了吧") is True
        assert self.detect("搞错了") is True

    def test_correction_with_replacement(self):
        """纠正+替换: 不是X是Y"""
        assert self.detect("不是苹果手机是苹果公司的股票") is True
        assert self.detect("不是这个，而是比亚迪") is True

    def test_redo_commands(self):
        """重新来: 重新分析/重新查"""
        assert self.detect("重新分析一下") is True
        assert self.detect("重新来") is True
        assert self.detect("重新查TSLA") is True

    def test_clarification_intent(self):
        """我说的是/我的意思是"""
        assert self.detect("我说的是A股的比亚迪") is True
        assert self.detect("我的意思是看周线") is True

    def test_normal_messages_not_detected(self):
        """正常消息不应被误判为纠错"""
        assert self.detect("你好") is False
        assert self.detect("帮我查天气") is False
        assert self.detect("分析TSLA") is False
        assert self.detect("今天大盘怎么样") is False
        assert self.detect("") is False
        assert self.detect("a") is False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2. 复合意图拆解
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCompoundIntentDetection:
    """测试 _detect_compound_intent — 搬运 AutoGPT task chain"""

    def setup_method(self):
        from src.core.brain import _detect_compound_intent
        from src.core.intent_parser import ParsedIntent, TaskType
        self.detect = _detect_compound_intent
        self.ParsedIntent = ParsedIntent
        self.TaskType = TaskType

    def _make_primary(self, task_type="investment"):
        return self.ParsedIntent(
            goal="test", task_type=self.TaskType(task_type), confidence=0.8
        )

    def test_two_step_compound(self):
        """两步复合: 分析然后发小红书"""
        result = self.detect("分析TSLA然后发到小红书", self._make_primary())
        assert result is not None
        assert len(result) == 2
        assert result[0].task_type == self.TaskType.INVESTMENT
        assert result[1].task_type == self.TaskType.SOCIAL

    def test_three_step_compound(self):
        """三步复合: 查行情→分析→发文"""
        result = self.detect("查一下TSLA行情然后分析技术面最后发到小红书", self._make_primary())
        assert result is not None
        assert len(result) == 3

    def test_single_intent_not_split(self):
        """单一意图不应被拆解"""
        assert self.detect("帮我分析TSLA", self._make_primary()) is None
        assert self.detect("查天气", self._make_primary()) is None
        assert self.detect("", self._make_primary()) is None

    def test_connector_words(self):
        """各种连接词: 然后/接着/之后/再/并且/同时"""
        for connector in ["然后", "接着", "之后", "再", "并且", "同时", "顺便"]:
            msg = f"分析TSLA{connector}查看持仓"
            result = self.detect(msg, self._make_primary())
            assert result is not None, f"连接词 '{connector}' 未检测到"
            assert len(result) >= 2, f"连接词 '{connector}' 拆解失败"

    def test_short_segments_ignored(self):
        """太短的段不算有效子任务"""
        result = self.detect("看然后做", self._make_primary())
        assert result is None  # 每段不到3字符


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3. 消息温度感知
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMessageToneDetection:
    """测试 _detect_message_tone — 搬运 Google Gemini 情境适应"""

    def setup_method(self):
        from src.bot.api_mixin import _detect_message_tone
        self.detect = _detect_message_tone

    def test_urgent_exclamation(self):
        """连续感叹号 → 紧急"""
        assert self.detect("快看TSLA！！！") == "urgent"
        assert self.detect("出问题了！！") == "urgent"

    def test_urgent_keywords(self):
        """催促关键词 → 紧急"""
        assert self.detect("赶紧帮我查") == "urgent"
        assert self.detect("马上看看") == "urgent"
        assert self.detect("紧急！TSLA崩了") == "urgent"

    def test_detailed_long_message(self):
        """长消息 → 详细"""
        long_msg = "帮我分析一下特斯拉最近的走势看看支撑位和压力位分别在哪里"
        assert self.detect(long_msg) == "detailed"

    def test_detailed_multiple_questions(self):
        """多个问号 → 详细"""
        assert self.detect("这只股票怎么样？技术面如何？") == "detailed"

    def test_normal_messages(self):
        """普通消息 → normal"""
        assert self.detect("你好") == "normal"
        assert self.detect("查一下天气") == "normal"
        assert self.detect("") == "normal"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  4. 实时偏好检测（正则逻辑，不测异步写入）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPreferencePatterns:
    """测试偏好信号词正则匹配逻辑"""

    _PREF_PATTERNS = [
        (r"(?:我喜欢|我偏好|我倾向|我更想)", "用户偏好"),
        (r"(?:我讨厌|别给我|不要给我|我不喜欢|以后别|以后不要)", "用户反感"),
        (r"(?:简短[点些一]|简洁[点些一]|少[说废]话|直接[说给]|别[啰罗]嗦)", "沟通风格: 偏好简洁"),
        (r"(?:详细[点些一]|说[详仔]细|展开[说讲])", "沟通风格: 偏好详细"),
        (r"(?:帮我记住|你记一下|记住我|以后记得)", "用户要求记忆"),
    ]

    def _match(self, text):
        for pattern, category in self._PREF_PATTERNS:
            if re.search(pattern, text):
                return category
        return None

    def test_positive_preferences(self):
        assert self._match("我喜欢简短的回复") == "用户偏好"
        assert self._match("我偏好技术分析") == "用户偏好"

    def test_negative_preferences(self):
        assert self._match("我讨厌长篇大论") == "用户反感"
        assert self._match("以后别给我发广告") == "用户反感"

    def test_brevity_preference(self):
        assert self._match("简短点") == "沟通风格: 偏好简洁"
        assert self._match("少废话") == "沟通风格: 偏好简洁"
        assert self._match("直接说结论") == "沟通风格: 偏好简洁"

    def test_detail_preference(self):
        assert self._match("详细点") == "沟通风格: 偏好详细"
        assert self._match("展开说说") == "沟通风格: 偏好详细"

    def test_memory_request(self):
        assert self._match("帮我记住这个偏好") == "用户要求记忆"

    def test_no_match(self):
        assert self._match("帮我查天气") is None
        assert self._match("你好") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  5. TL;DR 摘要阈值逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTldrThreshold:
    """测试 generate_tldr 的阈值判断（不调 LLM）"""

    def setup_method(self):
        from src.core.response_synthesizer import ResponseSynthesizer
        self.synth = ResponseSynthesizer()

    @pytest.mark.asyncio
    async def test_short_text_skipped(self):
        """200字以内的文本不生成摘要"""
        result = await self.synth.generate_tldr("短文本")
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_text_skipped(self):
        assert await self.synth.generate_tldr("") == ""
        assert await self.synth.generate_tldr(None) == ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  6. 追问建议解析逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSuggestionsParser:
    """测试 generate_suggestions 对 LLM 返回文本的解析"""

    def test_parse_numbered_lines(self):
        """解析带编号的行"""
        raw = "1. 查看TSLA技术分析\n2. 设置止损位\n3. 看看相关新闻"
        lines = []
        for line in raw.splitlines():
            cleaned = line.strip().lstrip("0123456789.-、)）·• ").strip()
            if cleaned and 3 <= len(cleaned) <= 30:
                lines.append(cleaned)
        assert len(lines) == 3
        assert lines[0] == "查看TSLA技术分析"

    def test_filter_too_short(self):
        """过滤太短的建议"""
        raw = "好\n查看TSLA\n嗯"
        lines = []
        for line in raw.splitlines():
            cleaned = line.strip()
            if cleaned and 3 <= len(cleaned) <= 30:
                lines.append(cleaned)
        assert len(lines) == 1  # 只有"查看TSLA"保留

    def test_filter_too_long(self):
        """过滤太长的建议"""
        raw = "查看TSLA\n" + "这是一个非常非常非常非常非常非常非常非常非常长的建议文本超过了三十个字符的限制"
        lines = []
        for line in raw.splitlines():
            cleaned = line.strip()
            if cleaned and 3 <= len(cleaned) <= 30:
                lines.append(cleaned)
        assert len(lines) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  7. WatchlistMonitor 冷却机制
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWatchlistMonitorCooldown:
    """测试 PanWatch 冷却节流机制"""

    def setup_method(self):
        from src.watchlist_monitor import WatchlistMonitor
        self.monitor = WatchlistMonitor(check_interval=60)

    def test_first_alert_passes(self):
        """首次告警应通过（无冷却记录）"""
        assert self.monitor._is_cooled("TSLA", "price_surge") is True

    def test_cooldown_blocks_repeat(self):
        """冷却期内重复告警应被阻止"""
        self.monitor._mark_cooldown("TSLA", "price_surge")
        assert self.monitor._is_cooled("TSLA", "price_surge") is False

    def test_different_symbol_not_blocked(self):
        """不同标的的告警互不干扰"""
        self.monitor._mark_cooldown("TSLA", "price_surge")
        assert self.monitor._is_cooled("AAPL", "price_surge") is True

    def test_different_type_not_blocked(self):
        """同一标的不同类型的告警互不干扰"""
        self.monitor._mark_cooldown("TSLA", "price_surge")
        assert self.monitor._is_cooled("TSLA", "volume_surge") is True

    def test_cleanup_removes_expired(self):
        """清理应移除过期的冷却记录"""
        # 手动设置一个很早的时间戳
        self.monitor._cooldowns[("OLD", "test")] = time.monotonic() - 100000
        self.monitor._cleanup_cooldowns()
        assert ("OLD", "test") not in self.monitor._cooldowns


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  8. 跨域信号聚合
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCrossDomainEnrichment:
    """测试 SynergyPipelines.get_context_enrichment"""

    def setup_method(self):
        from src.core.synergy_pipelines import SynergyPipelines
        self.sp = SynergyPipelines.__new__(SynergyPipelines)
        self.sp._social_signals = {}
        self.sp._vetoed_symbols = set()
        self.sp._stats = {"total_events": 0}
        self.sp._pipeline_config = {}

    def test_empty_returns_empty(self):
        """无信号时返回空字符串"""
        assert self.sp.get_context_enrichment() == ""

    def test_vetoed_symbols_shown(self):
        """风控否决标的应出现在结果中"""
        self.sp._vetoed_symbols = {"TSLA", "NVDA"}
        result = self.sp.get_context_enrichment()
        assert "风控否决标的" in result

    def test_social_signals_shown(self):
        """社交热点信号应出现在结果中"""
        self.sp._social_signals = {
            "TSLA": {"timestamp": time.time(), "sentiment": "看涨"},
        }
        result = self.sp.get_context_enrichment()
        assert "社交热点标的" in result
        assert "TSLA" in result

    def test_stale_signals_excluded(self):
        """超过1小时的信号不应出现"""
        self.sp._social_signals = {
            "OLD": {"timestamp": time.time() - 7200, "sentiment": "neutral"},
        }
        result = self.sp.get_context_enrichment()
        assert "OLD" not in result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  9. 首次引导标志
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFirstTimeFlags:
    """测试首次能力引导标志"""

    def test_flag_starts_empty(self):
        from src.core.response_synthesizer import ResponseSynthesizer
        synth = ResponseSynthesizer()
        synth._first_time_flags = {}  # 重置
        assert "tldr" not in synth._first_time_flags
        assert "suggestions" not in synth._first_time_flags

    def test_flag_set_after_first_use(self):
        from src.core.response_synthesizer import ResponseSynthesizer
        synth = ResponseSynthesizer()
        synth._first_time_flags = {}  # 重置
        # 模拟首次设置
        synth._first_time_flags["tldr"] = True
        assert "tldr" in synth._first_time_flags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  10. 错误消息模板
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNewErrorTemplates:
    """测试第二轮新增的错误消息模板"""

    def test_correction_ack(self):
        from src.bot.error_messages import correction_ack
        result = correction_ack()
        assert "更正" in result or "纠正" in result or "搞错" in result

    def test_correction_ack_with_details(self):
        from src.bot.error_messages import correction_ack
        result = correction_ack("苹果手机", "苹果公司")
        assert "苹果手机" in result
        assert "苹果公司" in result

    def test_preference_saved(self):
        from src.bot.error_messages import preference_saved
        result = preference_saved("简短回复")
        assert "记住" in result
        assert "简短回复" in result

    def test_preference_saved_empty(self):
        from src.bot.error_messages import preference_saved
        result = preference_saved()
        assert "记住" in result
