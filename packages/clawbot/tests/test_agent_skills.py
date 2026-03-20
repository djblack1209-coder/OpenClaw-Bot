"""测试 Agent 技能系统"""
import pytest
from src.agent_skills import (
    AgentSkill, AgentProfile, SkillCategory, SkillLevel,
    SkillRegistry, WorkflowComposer, AgentTask, TaskStatus,
)


def test_agent_profile():
    """测试 Agent 能力画像"""
    skill = AgentSkill(
        name="code", description="编程", category=SkillCategory.CODE,
        level=SkillLevel.EXPERT, keywords=["代码", "编程"]
    )
    profile = AgentProfile(agent_id="test_bot", name="Test", skills=[skill])
    
    assert profile.is_available
    assert profile.has_skill("code")
    assert profile.get_skill_level("code") == SkillLevel.EXPERT
    assert profile.skill_score(SkillCategory.CODE) == 100
    
    profile.record_quality(0.8)
    assert profile.avg_quality == 0.8


def test_skill_registry():
    """测试技能注册中心"""
    registry = SkillRegistry()
    
    skill1 = AgentSkill("analysis", "分析", SkillCategory.ANALYSIS, SkillLevel.EXPERT)
    profile1 = AgentProfile("bot1", "Bot1", [skill1])
    registry.register_agent(profile1)
    
    # 按技能查找
    agent_id = registry.find_agent_for_skill("analysis")
    assert agent_id == "bot1"
    
    # 按分类查找
    agents = registry.find_agents_for_category(SkillCategory.ANALYSIS)
    assert "bot1" in agents
    
    # 列出所有
    all_agents = registry.list_agents()
    assert len(all_agents) == 1


def test_workflow_composer():
    """测试工作流编排"""
    registry = SkillRegistry()
    skill = AgentSkill("code", "编程", SkillCategory.CODE, SkillLevel.EXPERT)
    profile = AgentProfile("coder", "Coder", [skill])
    registry.register_agent(profile)
    
    composer = WorkflowComposer(registry)
    
    # 分解任务
    tasks = composer.decompose_task("开发一个功能", "wf_test")
    assert len(tasks) >= 1
    
    # 分配 Agent
    assignments = composer.assign_agents(tasks)
    assert len(assignments) > 0
    
    # 创建工作流
    wf_id, steps = composer.create_workflow("开发功能")
    assert len(steps) > 0
    
    # 完成任务
    if steps:
        task_id = steps[0].task.task_id
        composer.complete_task(task_id, "完成", 0.9)
        status = composer.get_workflow_status(wf_id)
        assert status["completed"] == 1
