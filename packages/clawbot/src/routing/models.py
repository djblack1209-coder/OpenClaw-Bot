"""
Routing — 常量和数据模型
从 chat_router.py 提取的常量、枚举、数据类
"""
import time
from enum import Enum
from typing import Dict, List, Any
from dataclasses import dataclass, field


# ── 意图分类 ────────────────────────────────────────────────

class Intent:
    CODE = "code"
    MATH = "math"
    CREATIVE = "creative"
    KNOWLEDGE = "knowledge"
    GENERAL = "general"
    IMAGE = "image"
    ANALYSIS = "analysis"


INTENT_KEYWORDS = {
    Intent.CODE: [
        "代码", "编程", "python", "javascript", "java", "bug", "debug",
        "函数", "class", "api", "sql", "html", "css", "react", "vue",
        "git", "docker", "linux", "bash", "shell", "npm", "pip",
        "编译", "报错", "异常", "exception", "error", "import",
        "数据库", "算法", "数据结构", "正则", "regex",
    ],
    Intent.MATH: [
        "计算", "数学", "方程", "概率", "统计", "微积分", "线性代数",
        "矩阵", "向量", "几何", "三角", "对数", "指数",
    ],
    Intent.CREATIVE: [
        "写", "故事", "诗", "小说", "文案", "创意", "剧本", "歌词",
        "翻译", "润色", "改写", "摘要", "总结", "大纲",
    ],
    Intent.KNOWLEDGE: [
        "历史", "地理", "科学", "物理", "化学", "生物", "哲学",
        "经济", "政治", "法律", "医学", "心理", "文化", "艺术",
    ],
    Intent.IMAGE: [
        "画", "图片", "图像", "生成图", "画一", "设计", "logo",
        "插画", "海报", "壁纸",
    ],
    Intent.ANALYSIS: [
        "分析", "对比", "评估", "优缺点", "利弊", "趋势",
        "预测", "研究", "调研", "报告",
    ],
}

# 意图 -> 最佳 bot 映射
INTENT_BOT_MAP = {
    Intent.CODE: ["claude_sonnet", "qwen235b", "deepseek_v3"],
    Intent.MATH: ["claude_sonnet", "qwen235b", "deepseek_v3"],
    Intent.CREATIVE: ["deepseek_v3", "claude_sonnet", "qwen235b"],
    Intent.KNOWLEDGE: ["deepseek_v3", "qwen235b", "claude_sonnet"],
    Intent.GENERAL: ["qwen235b", "gptoss", "claude_haiku"],
    Intent.IMAGE: ["qwen235b", "claude_haiku"],
    Intent.ANALYSIS: ["claude_sonnet", "deepseek_v3", "qwen235b"],
}

# 显式 lane 路由规则
LANE_ROUTE_RULES = [
    ("#code", "claude_sonnet"),
    ("#risk", "claude_sonnet"),
    ("#creative", "deepseek_v3"),
    ("#chinese", "deepseek_v3"),
    ("#fast", "claude_haiku"),
    ("#quick", "gptoss"),
    ("#free", "free_llm"),
    ("#opus", "claude_opus"),
]

_FALLBACK_ROTATION = ["qwen235b", "gptoss", "claude_haiku", "deepseek_v3"]

# 链式讨论触发词
CHAIN_DISCUSS_TRIGGERS = [
    "所有人", "所有bot", "所有机器人", "大家讨论", "大家说说",
    "每个人", "按顺序", "依次讨论", "轮流", "大家聊聊",
    "大家来聊聊", "大家来讨论", "一起讨论", "各位说说",
    "大家分析", "大家看看", "每个bot", "所有ai",
    "链式讨论", "客服模式", "协同处理", "ai团队处理", "大家一起做",
    "everyone discuss", "all bots",
]

# 服务工作流检测
SERVICE_WORKFLOW_ACTION_HINTS = [
    "帮我", "帮忙", "麻烦", "请你", "实现", "修复", "优化", "排查", "部署", "接入",
    "配置", "设计", "重构", "整理", "梳理", "写", "规划", "方案", "评审", "完善",
    "补充", "检查", "搭建", "迁移", "上线", "排版", "公告", "流程", "自动化", "更新",
]

SERVICE_WORKFLOW_NOUN_HINTS = [
    "代码", "功能", "接口", "页面", "系统", "项目", "文案", "排版", "公告", "流程",
    "群聊", "机器人", "配置", "部署", "bug", "报错", "任务", "执行", "结构", "方案",
    "脚本", "网站", "服务", "提示词", "工作流", "自动化",
]

SERVICE_WORKFLOW_SKIP_HINTS = [
    "直接回答", "直接说", "直接给结果", "一句话回答", "快答", "别问我", "不要问我",
    "不用问我", "不要方案", "不用方案", "先别分工", "单独回答",
]


# ── 数据类 ──────────────────────────────────────────────────

@dataclass
class BotCapability:
    """Bot 能力描述"""
    bot_id: str
    name: str
    username: str
    keywords: List[str]
    domains: List[str]
    priority: int = 0


@dataclass
class ServiceWorkflowSession:
    session_id: str
    chat_id: int
    original_text: str
    owner_bot_id: str
    intake_bot_id: str
    expert_bot_id: str
    director_bot_id: str
    stage: str = "awaiting_selection"
    active: bool = True
    options: List[Dict[str, Any]] = field(default_factory=list)
    intake_summary: str = ""
    missing_info: List[str] = field(default_factory=list)
    selected_option_id: int = 0
    selection_note: str = ""
    expert_plan: Dict[str, Any] = field(default_factory=dict)
    team_plan: Dict[str, Any] = field(default_factory=dict)
    execution_results: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    final_report: str = ""
    rating_hint: str = ""
    created_at: float = field(default_factory=time.time)


class CollabPhase(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    SUMMARIZING = "summarizing"
    DONE = "done"


@dataclass
class CollabTask:
    task_id: str
    chat_id: int
    original_text: str
    planner_bot_id: str
    executor_bot_id: str
    reviewer_bot_id: str
    summarizer_bot_id: str
    phase: CollabPhase = CollabPhase.PLANNING
    plan: str = ""
    execution_result: str = ""
    review_result: str = ""
    summary: str = ""
    review_count: int = 0
    max_reviews: int = 2
    created_at: float = field(default_factory=time.time)


class MessagePriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class PrioritizedMessage:
    priority: int
    timestamp: float
    chat_id: int
    user_id: int
    text: str
    bot_id: str = ""

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp
