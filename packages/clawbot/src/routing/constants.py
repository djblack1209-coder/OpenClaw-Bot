"""
路由常量定义 — 意图关键词、分流规则、触发词等
从 chat_router.py 拆分而来，集中管理所有路由相关常量。
"""
from src.constants import (
    BOT_QWEN, BOT_DEEPSEEK, BOT_GPTOSS,
    BOT_CLAUDE_HAIKU, BOT_CLAUDE_SONNET, BOT_CLAUDE_OPUS,
)

# 链式讨论触发词（统一定义，避免重复）
CHAIN_DISCUSS_TRIGGERS = [
    "所有人", "所有bot", "所有机器人", "大家讨论", "大家说说",
    "每个人", "按顺序", "依次讨论", "轮流", "大家聊聊",
    "大家来聊聊", "大家来讨论", "一起讨论", "各位说说",
    "大家分析", "大家看看", "每个bot", "所有ai",
    "链式讨论", "客服模式", "协同处理", "ai团队处理", "大家一起做",
    "everyone discuss", "all bots",
]

# 服务工作流动作类关键词（判断是否为任务请求）
SERVICE_WORKFLOW_ACTION_HINTS = [
    "帮我", "帮忙", "麻烦", "请你", "实现", "修复", "优化", "排查", "部署", "接入",
    "配置", "设计", "重构", "整理", "梳理", "写", "规划", "方案", "评审", "完善",
    "补充", "检查", "搭建", "迁移", "上线", "排版", "公告", "流程", "自动化", "更新",
]

# 服务工作流名词类关键词（配合动作词判断任务请求）
SERVICE_WORKFLOW_NOUN_HINTS = [
    "代码", "功能", "接口", "页面", "系统", "项目", "文案", "排版", "公告", "流程",
    "群聊", "机器人", "配置", "部署", "bug", "报错", "任务", "执行", "结构", "方案",
    "脚本", "网站", "服务", "提示词", "工作流", "自动化",
]

# 用户明确要求跳过工作流时的关键词
SERVICE_WORKFLOW_SKIP_HINTS = [
    "直接回答", "直接说", "直接给结果", "一句话回答", "快答", "别问我", "不要问我",
    "不用问我", "不要方案", "不用方案", "先别分工", "单独回答",
]


# 意图分类标签
class Intent:
    """消息意图类型常量"""
    CODE = "code"                 # 编程相关
    MATH = "math"                 # 数学/逻辑
    CREATIVE = "creative"         # 创意/写作
    KNOWLEDGE = "knowledge"       # 知识/历史/文化
    GENERAL = "general"           # 通用问答
    IMAGE = "image"               # 图片生成
    ANALYSIS = "analysis"         # 分析/推理


# 意图 -> 最佳 bot 映射（每个 bot 至少有一个 rank 0 场景）
INTENT_BOT_MAP = {
    Intent.CODE: [BOT_DEEPSEEK, BOT_QWEN, BOT_CLAUDE_OPUS],
    Intent.MATH: [BOT_DEEPSEEK, BOT_QWEN],
    Intent.CREATIVE: [BOT_CLAUDE_SONNET, BOT_CLAUDE_HAIKU],
    Intent.KNOWLEDGE: [BOT_QWEN, BOT_CLAUDE_HAIKU],
    Intent.GENERAL: [BOT_GPTOSS, BOT_QWEN],
    Intent.IMAGE: [BOT_CLAUDE_SONNET],
    Intent.ANALYSIS: [BOT_CLAUDE_OPUS, BOT_CLAUDE_SONNET, BOT_DEEPSEEK],
}

# 显式分流通道（topic/forum 不可用时的替代方案）
# 规则：用户在消息里带上 lane marker，即可强制路由到指定 bot。
LANE_ROUTE_RULES = [
    ("risk", BOT_CLAUDE_SONNET, ["[risk]", "#risk", "#风控", "#风险"]),
    ("alpha", BOT_QWEN, ["[alpha]", "#alpha", "#研究", "#策略"]),
    ("exec", BOT_DEEPSEEK, ["[exec]", "#exec", "#执行", "#下单"]),
    ("fast", BOT_GPTOSS, ["[fast]", "#fast", "#快问", "#速答"]),
    ("cn", BOT_DEEPSEEK, ["[cn]", "#cn", "#中文"]),
    ("brain", BOT_CLAUDE_OPUS, ["[brain]", "#brain", "#终极", "#深度"]),
    ("creative", BOT_CLAUDE_HAIKU, ["[creative]", "#creative", "#文案", "#创意"]),
]

# 兜底轮换列表（排除付费 Opus 和 Free-LLM，其余 5 个 bot 轮换）
FALLBACK_ROTATION = [BOT_QWEN, BOT_GPTOSS, BOT_DEEPSEEK, BOT_CLAUDE_HAIKU, BOT_CLAUDE_SONNET]

# 意图检测关键词表
INTENT_KEYWORDS = {
    Intent.CODE: [
        "代码", "编程", "bug", "报错", "函数", "class", "def ", "import ",
        "python", "java", "javascript", "typescript", "rust", "go",
        "api", "接口", "数据库", "sql", "git", "docker", "部署",
        "调试", "debug", "编译", "运行", "脚本",
    ],
    Intent.MATH: [
        "计算", "数学", "公式", "方程", "概率", "统计", "证明",
        "算法", "复杂度", "推导", "求解", "积分", "微分",
        "逻辑", "推理", "矛盾", "悖论",
    ],
    Intent.CREATIVE: [
        "写一", "创作", "故事", "小说", "诗", "文案", "广告",
        "创意", "灵感", "想象", "设计", "策划", "营销",
        "感觉", "情感", "心情", "建议", "人生",
    ],
    Intent.KNOWLEDGE: [
        "历史", "文化", "哲学", "文学", "典故", "朝代",
        "科学", "物理", "化学", "生物", "地理",
        "解释", "为什么", "原理", "概念", "理论",
    ],
    Intent.IMAGE: [
        "画", "图片", "生成图", "draw", "图像", "照片",
    ],
    Intent.ANALYSIS: [
        "分析", "对比", "优缺点", "评估", "判断",
        "怎么选", "哪个好", "利弊", "风险",
    ],
}
