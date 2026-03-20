"""
ClawBot Agent 技能系统 v1.0（对标 OpenAI Agents SDK 20.1k⭐ + MetaGPT 65.3k⭐）

功能：
- 可复用的 Agent 技能定义与注册
- 按能力自动匹配最佳 Agent
- 动态工作流编排（任务分解 -> Agent 分配 -> 执行 -> 汇总）
- 技能组合与依赖管理
- 执行追踪与质量评估
- 与现有 chat_router / collab_orchestrator 兼容

设计原则（对标 OpenAI Agents SDK）：
- Agents: 配置了指令、技能、护栏的 LLM
- Handoffs: Agent 间任务委托
- Tools: Agent 可调用的工具
- Guardrails: 输入输出安全检查
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============ 技能定义 ============

class SkillCategory(Enum):
    """技能分类"""
    CODE = "code"               # 编程开发
    ANALYSIS = "analysis"       # 数据分析
    CREATIVE = "creative"       # 创意写作
    TRADING = "trading"         # 交易投资
    RESEARCH = "research"       # 研究调研
    SOCIAL = "social"           # 社媒运营
    SYSTEM = "system"           # 系统运维
    GENERAL = "general"         # 通用能力


class SkillLevel(Enum):
    """技能熟练度"""
    EXPERT = "expert"           # 专家级
    ADVANCED = "advanced"       # 高级
    INTERMEDIATE = "intermediate"  # 中级
    BASIC = "basic"             # 基础


@dataclass
class AgentSkill:
    """可复用的 Agent 技能定义（对标 OpenAI Agents SDK Tools）"""
    name: str                           # 技能名称
    description: str                    # 技能描述
    category: SkillCategory             # 技能分类
    level: SkillLevel = SkillLevel.INTERMEDIATE  # 熟练度
    keywords: List[str] = field(default_factory=list)  # 触发关键词
    required_capabilities: List[str] = field(default_factory=list)  # 所需能力
    estimated_time_sec: float = 30.0    # 预估执行时间
    cost_tier: str = "free"             # 成本等级: free/low/medium/high
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他技能
    version: str = "1.0"


@dataclass
class AgentProfile:
    """Agent 能力画像（对标 MetaGPT Role）"""
    agent_id: str                       # bot_id
    name: str                           # 显示名
    skills: List[AgentSkill] = field(default_factory=list)
    max_concurrent_tasks: int = 3       # 最大并发任务数
    current_tasks: int = 0              # 当前任务数
    total_completed: int = 0            # 累计完成任务数
    avg_quality: float = 0.5            # 平均质量评分 (0-1)
    _quality_sum: float = 0.0
    _quality_count: int = 0

    def record_quality(self, score: float):
        """记录任务质量评分"""
        self._quality_sum += max(0, min(1, score))
        self._quality_count += 1
        self.avg_quality = self._quality_sum / self._quality_count

    @property
    def is_available(self) -> bool:
        return self.current_tasks < self.max_concurrent_tasks

    def has_skill(self, skill_name: str) -> bool:
        return any(s.name == skill_name for s in self.skills)

    def get_skill_level(self, skill_name: str) -> Optional[SkillLevel]:
        for s in self.skills:
            if s.name == skill_name:
                return s.level
        return None

    def skill_score(self, category: SkillCategory) -> float:
        """计算 Agent 在某个分类上的综合技能分"""
        level_scores = {
            SkillLevel.EXPERT: 100,
            SkillLevel.ADVANCED: 75,
            SkillLevel.INTERMEDIATE: 50,
            SkillLevel.BASIC: 25,
        }
        matching = [s for s in self.skills if s.category == category]
        if not matching:
            return 0
        return max(level_scores.get(s.level, 25) for s in matching)


# ============ 任务定义 ============

class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentTask:
    """Agent 任务（对标 MetaGPT Action）"""
    task_id: str
    description: str
    category: SkillCategory = SkillCategory.GENERAL
    required_skills: List[str] = field(default_factory=list)
    assigned_agent: str = ""            # 分配的 agent_id
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5                   # 1-10, 10 最高
    result: str = ""
    quality_score: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    parent_task_id: str = ""            # 父任务 ID（用于子任务）
    subtasks: List[str] = field(default_factory=list)  # 子任务 ID 列表
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStep:
    """工作流步骤"""
    step_id: int
    task: AgentTask
    depends_on: List[int] = field(default_factory=list)  # 依赖的步骤 ID
    parallel: bool = False              # 是否可并行执行


# ============ 技能注册中心 ============

class SkillRegistry:
    """技能注册中心（对标 OpenAI Agents SDK ToolRegistry）

    管理所有 Agent 的技能注册、查询、匹配。
    """

    def __init__(self):
        self._agents: Dict[str, AgentProfile] = {}
        self._skills_index: Dict[str, List[str]] = {}  # skill_name -> [agent_ids]
        self._category_index: Dict[str, List[str]] = {}  # category -> [agent_ids]
        self._keyword_index: Dict[str, List[Tuple[str, str]]] = {}  # keyword -> [(agent_id, skill_name)]

    def register_agent(self, profile: AgentProfile):
        """注册 Agent 及其技能"""
        self._agents[profile.agent_id] = profile
        for skill in profile.skills:
            # 技能名索引
            if skill.name not in self._skills_index:
                self._skills_index[skill.name] = []
            if profile.agent_id not in self._skills_index[skill.name]:
                self._skills_index[skill.name].append(profile.agent_id)

            # 分类索引
            cat = skill.category.value
            if cat not in self._category_index:
                self._category_index[cat] = []
            if profile.agent_id not in self._category_index[cat]:
                self._category_index[cat].append(profile.agent_id)

            # 关键词索引
            for kw in skill.keywords:
                kw_lower = kw.lower()
                if kw_lower not in self._keyword_index:
                    self._keyword_index[kw_lower] = []
                self._keyword_index[kw_lower].append((profile.agent_id, skill.name))

        logger.info(
            "[SkillRegistry] 注册 Agent: %s (%d 个技能)",
            profile.agent_id, len(profile.skills)
        )

    def unregister_agent(self, agent_id: str):
        """注销 Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            # 清理索引
            for skill_agents in self._skills_index.values():
                if agent_id in skill_agents:
                    skill_agents.remove(agent_id)
            for cat_agents in self._category_index.values():
                if agent_id in cat_agents:
                    cat_agents.remove(agent_id)

    def find_agent_for_skill(self, skill_name: str) -> Optional[str]:
        """查找拥有指定技能的最佳 Agent"""
        agent_ids = self._skills_index.get(skill_name, [])
        if not agent_ids:
            return None
        # 按技能等级 + 可用性 + 质量评分排序
        candidates = []
        for aid in agent_ids:
            agent = self._agents.get(aid)
            if agent and agent.is_available:
                level = agent.get_skill_level(skill_name)
                level_score = {
                    SkillLevel.EXPERT: 100,
                    SkillLevel.ADVANCED: 75,
                    SkillLevel.INTERMEDIATE: 50,
                    SkillLevel.BASIC: 25,
                }.get(level, 0)
                score = level_score + agent.avg_quality * 20
                candidates.append((aid, score))
        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]

    def find_agents_for_category(
        self, category: SkillCategory, limit: int = 3
    ) -> List[str]:
        """查找擅长指定分类的 Agent 列表"""
        agent_ids = self._category_index.get(category.value, [])
        candidates = []
        for aid in agent_ids:
            agent = self._agents.get(aid)
            if agent and agent.is_available:
                score = agent.skill_score(category) + agent.avg_quality * 20
                candidates.append((aid, score))
        candidates.sort(key=lambda x: -x[1])
        return [c[0] for c in candidates[:limit]]

    def match_by_keywords(self, text: str) -> Optional[Tuple[str, str]]:
        """通过关键词匹配 Agent 和技能"""
        text_lower = text.lower()
        best_match = None
        best_score = 0
        for kw, entries in self._keyword_index.items():
            if kw in text_lower:
                for agent_id, skill_name in entries:
                    agent = self._agents.get(agent_id)
                    if agent and agent.is_available:
                        score = len(kw) + agent.avg_quality * 10
                        if score > best_score:
                            best_score = score
                            best_match = (agent_id, skill_name)
        return best_match

    def get_agent(self, agent_id: str) -> Optional[AgentProfile]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有已注册 Agent"""
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "skills": [s.name for s in a.skills],
                "available": a.is_available,
                "quality": round(a.avg_quality, 2),
                "completed": a.total_completed,
            }
            for a in self._agents.values()
        ]

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有已注册技能"""
        all_skills = {}
        for agent in self._agents.values():
            for skill in agent.skills:
                if skill.name not in all_skills:
                    all_skills[skill.name] = {
                        "name": skill.name,
                        "category": skill.category.value,
                        "description": skill.description,
                        "agents": [],
                    }
                all_skills[skill.name]["agents"].append(agent.agent_id)
        return list(all_skills.values())


# ============ 工作流编排器（对标 MetaGPT SOP） ============

class WorkflowComposer:
    """工作流编排器 — 自动任务分解与 Agent 分配

    对标 MetaGPT 的 SOP（标准操作流程）：
    - 将复杂任务分解为子任务
    - 根据技能要求自动分配 Agent
    - 管理任务依赖和执行顺序
    - 支持并行执行
    """

    # 任务分解模板（基于关键词的规则引擎）
    DECOMPOSITION_RULES = {
        "开发": [
            ("需求分析", SkillCategory.ANALYSIS, ["analysis", "research"]),
            ("架构设计", SkillCategory.CODE, ["architecture", "code"]),
            ("代码实现", SkillCategory.CODE, ["code", "implementation"]),
            ("代码审查", SkillCategory.CODE, ["code_review"]),
        ],
        "分析": [
            ("数据收集", SkillCategory.RESEARCH, ["research", "data_collection"]),
            ("数据分析", SkillCategory.ANALYSIS, ["analysis"]),
            ("报告撰写", SkillCategory.CREATIVE, ["writing", "report"]),
        ],
        "交易": [
            ("市场分析", SkillCategory.TRADING, ["market_analysis"]),
            ("风险评估", SkillCategory.TRADING, ["risk_assessment"]),
            ("策略制定", SkillCategory.TRADING, ["strategy"]),
            ("执行建议", SkillCategory.TRADING, ["execution"]),
        ],
        "社媒": [
            ("选题策划", SkillCategory.SOCIAL, ["content_planning"]),
            ("内容创作", SkillCategory.CREATIVE, ["writing", "creative"]),
            ("平台适配", SkillCategory.SOCIAL, ["platform_adaptation"]),
        ],
        "研究": [
            ("信息检索", SkillCategory.RESEARCH, ["search", "research"]),
            ("深度分析", SkillCategory.ANALYSIS, ["analysis"]),
            ("总结归纳", SkillCategory.CREATIVE, ["summarization"]),
        ],
    }

    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self._tasks: Dict[str, AgentTask] = {}
        self._workflows: Dict[str, List[WorkflowStep]] = {}

    def decompose_task(self, description: str, task_id: str = "") -> List[AgentTask]:
        """将复杂任务分解为子任务

        基于关键词匹配分解规则，生成子任务列表。
        """
        if not task_id:
            task_id = f"wf_{int(time.time() * 1000)}"

        # 匹配分解规则
        matched_rule = None
        for keyword, steps in self.DECOMPOSITION_RULES.items():
            if keyword in description:
                matched_rule = steps
                break

        if not matched_rule:
            # 无匹配规则，作为单一任务
            task = AgentTask(
                task_id=f"{task_id}_0",
                description=description,
                parent_task_id=task_id,
            )
            self._tasks[task.task_id] = task
            return [task]

        subtasks = []
        for i, (step_name, category, skills) in enumerate(matched_rule):
            task = AgentTask(
                task_id=f"{task_id}_{i}",
                description=f"[{step_name}] {description}",
                category=category,
                required_skills=skills,
                parent_task_id=task_id,
                priority=10 - i,  # 前面的步骤优先级更高
            )
            self._tasks[task.task_id] = task
            subtasks.append(task)

        return subtasks

    def assign_agents(self, tasks: List[AgentTask]) -> Dict[str, str]:
        """为任务列表自动分配 Agent

        Returns: {task_id: agent_id}
        """
        assignments = {}
        for task in tasks:
            agent_id = None

            # 优先按技能匹配
            for skill_name in task.required_skills:
                agent_id = self.registry.find_agent_for_skill(skill_name)
                if agent_id:
                    break

            # 其次按分类匹配
            if not agent_id:
                candidates = self.registry.find_agents_for_category(task.category)
                if candidates:
                    agent_id = candidates[0]

            if agent_id:
                task.assigned_agent = agent_id
                task.status = TaskStatus.ASSIGNED
                agent = self.registry.get_agent(agent_id)
                if agent:
                    agent.current_tasks += 1
                assignments[task.task_id] = agent_id

        return assignments

    def create_workflow(
        self, description: str, workflow_id: str = ""
    ) -> Tuple[str, List[WorkflowStep]]:
        """创建完整工作流：分解 -> 分配 -> 编排

        Returns: (workflow_id, steps)
        """
        if not workflow_id:
            workflow_id = f"wf_{int(time.time() * 1000)}"

        # 分解任务
        subtasks = self.decompose_task(description, workflow_id)

        # 分配 Agent
        self.assign_agents(subtasks)

        # 编排步骤（顺序依赖）
        steps = []
        for i, task in enumerate(subtasks):
            step = WorkflowStep(
                step_id=i,
                task=task,
                depends_on=[i - 1] if i > 0 else [],
                parallel=False,
            )
            steps.append(step)

        self._workflows[workflow_id] = steps
        logger.info(
            "[WorkflowComposer] 创建工作流 %s: %d 个步骤",
            workflow_id, len(steps)
        )
        return workflow_id, steps

    def complete_task(self, task_id: str, result: str, quality: float = 0.5):
        """标记任务完成"""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.quality_score = quality
        task.completed_at = time.time()

        # 更新 Agent 统计
        agent = self.registry.get_agent(task.assigned_agent)
        if agent:
            agent.current_tasks = max(0, agent.current_tasks - 1)
            agent.total_completed += 1
            agent.record_quality(quality)

    def fail_task(self, task_id: str, reason: str = ""):
        """标记任务失败"""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = TaskStatus.FAILED
        task.result = reason
        task.completed_at = time.time()

        agent = self.registry.get_agent(task.assigned_agent)
        if agent:
            agent.current_tasks = max(0, agent.current_tasks - 1)

    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """获取工作流状态"""
        steps = self._workflows.get(workflow_id, [])
        if not steps:
            return {"error": "工作流不存在"}

        total = len(steps)
        completed = sum(1 for s in steps if s.task.status == TaskStatus.COMPLETED)
        failed = sum(1 for s in steps if s.task.status == TaskStatus.FAILED)

        return {
            "workflow_id": workflow_id,
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "progress_pct": round(completed / max(total, 1) * 100, 1),
            "status": "completed" if completed == total else "failed" if failed > 0 else "in_progress",
            "steps": [
                {
                    "step": s.step_id,
                    "description": s.task.description,
                    "agent": s.task.assigned_agent,
                    "status": s.task.status.value,
                    "result_preview": s.task.result[:100] if s.task.result else "",
                }
                for s in steps
            ],
        }

    def get_all_workflows(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取所有工作流摘要"""
        results = []
        for wf_id in list(self._workflows.keys())[-limit:]:
            results.append(self.get_workflow_status(wf_id))
        return results


# ============ 预定义技能库 ============

# 对标 TradingAgents: 分析师团队技能
TRADING_SKILLS = [
    AgentSkill(
        name="market_analysis", description="市场趋势分析与行情解读",
        category=SkillCategory.TRADING, level=SkillLevel.EXPERT,
        keywords=["行情", "市场", "趋势", "大盘", "走势"],
    ),
    AgentSkill(
        name="technical_analysis", description="技术指标分析（RSI/MACD/布林带等）",
        category=SkillCategory.TRADING, level=SkillLevel.EXPERT,
        keywords=["技术分析", "RSI", "MACD", "K线", "均线"],
    ),
    AgentSkill(
        name="risk_assessment", description="风险评估与仓位管理",
        category=SkillCategory.TRADING, level=SkillLevel.ADVANCED,
        keywords=["风险", "仓位", "止损", "风控"],
    ),
    AgentSkill(
        name="strategy", description="交易策略制定与优化",
        category=SkillCategory.TRADING, level=SkillLevel.ADVANCED,
        keywords=["策略", "回测", "优化"],
    ),
]

# 对标 MetaGPT: 软件开发技能
CODE_SKILLS = [
    AgentSkill(
        name="code", description="代码编写与实现",
        category=SkillCategory.CODE, level=SkillLevel.EXPERT,
        keywords=["代码", "编程", "实现", "开发", "code", "python"],
    ),
    AgentSkill(
        name="architecture", description="系统架构设计",
        category=SkillCategory.CODE, level=SkillLevel.ADVANCED,
        keywords=["架构", "设计", "系统设计"],
    ),
    AgentSkill(
        name="code_review", description="代码审查与优化建议",
        category=SkillCategory.CODE, level=SkillLevel.ADVANCED,
        keywords=["审查", "review", "优化"],
    ),
    AgentSkill(
        name="debugging", description="Bug 排查与修复",
        category=SkillCategory.CODE, level=SkillLevel.ADVANCED,
        keywords=["bug", "调试", "排错", "debug"],
    ),
]

# 创意写作技能
CREATIVE_SKILLS = [
    AgentSkill(
        name="writing", description="文案撰写与创意写作",
        category=SkillCategory.CREATIVE, level=SkillLevel.EXPERT,
        keywords=["文案", "写作", "创意", "文章"],
    ),
    AgentSkill(
        name="summarization", description="内容总结与摘要",
        category=SkillCategory.CREATIVE, level=SkillLevel.ADVANCED,
        keywords=["总结", "摘要", "归纳"],
    ),
    AgentSkill(
        name="translation", description="多语言翻译",
        category=SkillCategory.CREATIVE, level=SkillLevel.ADVANCED,
        keywords=["翻译", "translate", "英文", "中文"],
    ),
]

# 研究分析技能
RESEARCH_SKILLS = [
    AgentSkill(
        name="research", description="深度研究与信息检索",
        category=SkillCategory.RESEARCH, level=SkillLevel.EXPERT,
        keywords=["研究", "调研", "搜索", "查找"],
    ),
    AgentSkill(
        name="analysis", description="数据分析与推理",
        category=SkillCategory.ANALYSIS, level=SkillLevel.EXPERT,
        keywords=["分析", "推理", "数据", "逻辑"],
    ),
    AgentSkill(
        name="data_collection", description="数据收集与整理",
        category=SkillCategory.RESEARCH, level=SkillLevel.INTERMEDIATE,
        keywords=["数据收集", "整理", "汇总"],
    ),
]

# 社媒运营技能
SOCIAL_SKILLS = [
    AgentSkill(
        name="content_planning", description="社媒内容策划",
        category=SkillCategory.SOCIAL, level=SkillLevel.ADVANCED,
        keywords=["选题", "策划", "内容计划"],
    ),
    AgentSkill(
        name="platform_adaptation", description="多平台内容适配（X/小红书）",
        category=SkillCategory.SOCIAL, level=SkillLevel.ADVANCED,
        keywords=["小红书", "X", "Twitter", "平台"],
    ),
]


# ============ 默认 Agent 技能配置（与 bot_profiles 对应） ============

DEFAULT_AGENT_SKILLS = {
    "qwen235b": {
        "name": "Qwen 235B",
        "skills": RESEARCH_SKILLS + [TRADING_SKILLS[0], CODE_SKILLS[0]],
    },
    "gptoss": {
        "name": "GPT-OSS 120B",
        "skills": [CREATIVE_SKILLS[2], RESEARCH_SKILLS[0], CODE_SKILLS[0]],  # 翻译、研究、代码
    },
    "claude_sonnet": {
        "name": "Claude Sonnet",
        "skills": [CODE_SKILLS[1], TRADING_SKILLS[2], RESEARCH_SKILLS[1]],  # 架构、风控、分析
    },
    "claude_haiku": {
        "name": "Claude Haiku",
        "skills": CREATIVE_SKILLS + SOCIAL_SKILLS,  # 创意写作 + 社媒
    },
    "deepseek_v3": {
        "name": "DeepSeek V3",
        "skills": CODE_SKILLS + [RESEARCH_SKILLS[1]],  # 全栈开发 + 分析
    },
    "claude_opus": {
        "name": "Claude Opus",
        "skills": [
            AgentSkill(
                name="deep_reasoning", description="深度推理与复杂问题求解",
                category=SkillCategory.ANALYSIS, level=SkillLevel.EXPERT,
                keywords=["深度推理", "复杂", "终极分析"],
            ),
            RESEARCH_SKILLS[1], TRADING_SKILLS[3],  # 分析 + 策略
        ],
    },
}


# ============ 全局实例 ============

skill_registry = SkillRegistry()
workflow_composer = WorkflowComposer(skill_registry)


def init_agent_skills():
    """初始化 Agent 技能系统（在 bot 启动后调用）"""
    for agent_id, config in DEFAULT_AGENT_SKILLS.items():
        profile = AgentProfile(
            agent_id=agent_id,
            name=config["name"],
            skills=config["skills"],
        )
        skill_registry.register_agent(profile)
    logger.info(
        "[AgentSkills] 技能系统已初始化: %d 个 Agent, %d 个技能",
        len(DEFAULT_AGENT_SKILLS),
        sum(len(c["skills"]) for c in DEFAULT_AGENT_SKILLS.values()),
    )
