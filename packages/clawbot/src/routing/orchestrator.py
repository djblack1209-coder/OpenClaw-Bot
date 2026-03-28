"""
CollabOrchestrator — 多 Bot 协作编排器
从 chat_router.py 拆分而来，实现「规划-执行-审查-汇总」四阶段协作流程。
"""
import re
import time
import logging
import asyncio
from typing import Dict, Optional, Callable, Awaitable

from src.routing.models import CollabPhase, CollabTask
from src.routing.router import ChatRouter

logger = logging.getLogger(__name__)


class CollabOrchestrator:
    """
    协作编排器 - 实现"规划-执行-审查-汇总"四阶段协作流程

    流程：
    1. 用户发送 /collab <任务描述>
    2. 路由器选择规划者（DeepSeek-R1 或 Qwen）
    3. 规划者分析任务，输出结构化执行计划
    4. Claude Opus 4.6 根据计划执行核心部分
    5. 规划者审查执行结果，不通过则修订重来
    6. ClawBot 汇总所有结果，输出最终答案
    """

    def __init__(self, router: ChatRouter):
        self.router = router
        self.active_tasks: Dict[str, CollabTask] = {}  # task_id -> CollabTask
        self._api_callers: Dict[str, Callable] = {}    # bot_id -> async api call func
        self._lock = asyncio.Lock()

    def register_api_caller(self, bot_id: str, caller: Callable[..., Awaitable[str]]):
        """注册 bot 的 API 调用函数"""
        self._api_callers[bot_id] = caller

    async def start_collab(
        self,
        chat_id: int,
        task_text: str,
        planner_override: Optional[str] = None,
    ) -> CollabTask:
        """
        启动协作任务。

        Args:
            chat_id: Telegram chat ID
            task_text: 用户的任务描述
            planner_override: 强制指定规划者（可选）

        Returns:
            CollabTask 对象
        """
        task_id = f"collab_{chat_id}_{int(time.time())}"

        # 选择规划者
        planner_id = planner_override or self.router.select_planner(task_text)

        task = CollabTask(
            task_id=task_id,
            chat_id=chat_id,
            original_text=task_text,
            planner_id=planner_id,
            reviewer_id=planner_id,  # 审查者默认与规划者相同
        )

        async with self._lock:
            self.active_tasks[task_id] = task

        logger.info(f"[Collab] 启动协作任务 {task_id}: 规划者={planner_id}, 任务={task_text[:50]}...")
        return task

    async def run_planning(self, task: CollabTask) -> str:
        """第一阶段：规划"""
        task.phase = CollabPhase.PLANNING
        planner = self._api_callers.get(task.planner_id)
        if not planner:
            task.error = f"规划者 {task.planner_id} 未注册"
            return task.error

        # 构造规划提示
        plan_prompt = f"""【协作任务 - 规划阶段】

你现在是协作团队的"规划师"。用户提出了以下任务，请你：

1. 分析任务的核心需求和难点
2. 将任务分解为具体的执行步骤
3. 标注哪些步骤是核心难点（将交给 Claude Opus 4.6 执行）
4. 标注哪些步骤是辅助性的

请用以下格式输出你的规划：

## 任务分析
（简要分析任务需求和难点）

## 执行计划
### 核心任务（交给 Claude Opus 4.6）
1. ...
2. ...

### 辅助任务
1. ...

## 注意事项
（执行时需要注意的要点）

---
用户任务：{task.original_text}"""

        try:
            result = await planner(task.chat_id, plan_prompt)
            task.plan_result = result
            logger.info(f"[Collab] {task.task_id} 规划完成 by {task.planner_id}")
            return result
        except Exception as e:
            task.error = f"规划失败: {e}"
            logger.error(f"[Collab] {task.task_id} 规划失败: {e}")
            return task.error

    async def run_execution(self, task: CollabTask) -> str:
        """第二阶段：执行（Claude Opus 4.6）"""
        task.phase = CollabPhase.EXECUTING
        executor = self._api_callers.get(task.executor_id)
        if not executor:
            task.error = f"执行者 {task.executor_id} 未注册"
            return task.error

        if not task.plan_result:
            task.error = "没有规划结果，无法执行"
            return task.error

        # 构造执行提示
        exec_prompt = f"""【协作任务 - 执行阶段】

你是协作团队的核心执行者（Claude Opus 4.6），团队中的规划师已经为以下任务制定了执行计划。
请你根据规划，高质量地完成核心任务部分。

## 原始任务
{task.original_text}

## 规划师的执行计划
{task.plan_result}

---
请根据以上规划，完成核心任务。输出你的执行结果，要求：
- 高质量、深入、全面
- 如果是代码任务，给出完整可运行的代码
- 如果是分析任务，给出深度分析
- 如果是创作任务，给出精心打磨的作品"""

        try:
            result = await executor(task.chat_id, exec_prompt)
            task.exec_result = result
            logger.info(f"[Collab] {task.task_id} 执行完成 by {task.executor_id}")
            return result
        except Exception as e:
            task.error = f"执行失败: {e}"
            logger.error(f"[Collab] {task.task_id} 执行失败: {e}")
            return task.error

    async def run_review(self, task: CollabTask) -> str:
        """
        审查阶段：规划者审查执行结果，判断是否达标。

        返回审查意见。如果不通过，task.review_passed = False，
        调用方可据此决定是否重新执行。
        """
        task.phase = CollabPhase.REVIEWING
        reviewer = self._api_callers.get(task.reviewer_id)
        if not reviewer:
            # 没有审查者，默认通过
            task.review_passed = True
            task.review_result = "（无审查者，自动通过）"
            return task.review_result

        review_prompt = f"""【协作任务 - 审查阶段】

你是协作团队的审查者。执行者（Claude Opus 4.6）已根据规划完成了任务，请你审查执行结果的质量。

## 原始任务
{task.original_text}

## 规划（你之前制定的）
{task.plan_result[:1500]}

## 执行结果
{task.exec_result[:3000]}

---
请审查执行结果，输出格式：

**审查结论**: PASS 或 REVISE
**评分**: 1-10
**评价**: （简要评价执行质量）
**改进建议**: （如果 REVISE，列出需要改进的具体点）

注意：
- 只有明显质量不足、遗漏关键内容、或有明显错误时才给 REVISE
- 一般性的小瑕疵给 PASS 即可，不要过于苛刻
- 评分 7 分以上应该给 PASS"""

        try:
            result = await reviewer(task.chat_id, review_prompt)
            task.review_result = result

            # 解析审查结论（使用正则匹配，更健壮）
            conclusion_match = re.search(
                r'审查结论[*\s:：]*\s*(PASS|REVISE)',
                result,
                re.IGNORECASE
            )
            if conclusion_match:
                task.review_passed = conclusion_match.group(1).upper() == "PASS"
            else:
                # 回退：如果没有匹配到格式化结论，检查全文
                has_revise = bool(re.search(r'\bREVISE\b', result, re.IGNORECASE))
                has_pass = bool(re.search(r'\bPASS\b', result, re.IGNORECASE))
                if has_revise and not has_pass:
                    task.review_passed = False
                else:
                    # 默认通过（宁可放行也不误拦）
                    task.review_passed = True

            logger.info(
                f"[Collab] {task.task_id} 审查完成 by {task.reviewer_id}, "
                f"passed={task.review_passed}"
            )
            return result
        except Exception as e:
            # 审查失败不阻塞流程，默认通过
            task.review_passed = True
            task.review_result = f"审查异常（自动通过）: {e}"
            logger.warning(f"[Collab] {task.task_id} 审查失败: {e}")
            return task.review_result

    async def run_revised_execution(self, task: CollabTask) -> str:
        """修订执行：根据审查意见重新执行"""
        task.phase = CollabPhase.EXECUTING
        task.retry_count += 1
        executor = self._api_callers.get(task.executor_id)
        if not executor:
            task.error = f"执行者 {task.executor_id} 未注册"
            return task.error

        revise_prompt = f"""【协作任务 - 修订执行】

你之前的执行结果未通过审查，请根据审查意见进行修订。

## 原始任务
{task.original_text}

## 规划
{task.plan_result[:1500]}

## 你之前的执行结果
{task.exec_result[:2000]}

## 审查意见
{task.review_result[:1500]}

---
请根据审查意见修订你的执行结果。重点改进审查中指出的问题。"""

        try:
            result = await executor(task.chat_id, revise_prompt)
            task.exec_result = result
            logger.info(f"[Collab] {task.task_id} 修订执行完成 (retry={task.retry_count})")
            return result
        except Exception as e:
            task.error = f"修订执行失败: {e}"
            logger.error(f"[Collab] {task.task_id} 修订执行失败: {e}")
            return task.error

    async def run_summary(self, task: CollabTask) -> str:
        """汇总阶段（ClawBot）- 包含审查信息"""
        task.phase = CollabPhase.SUMMARIZING
        summarizer = self._api_callers.get(task.summarizer_id)
        if not summarizer:
            task.error = f"汇总者 {task.summarizer_id} 未注册"
            return task.error

        # 构造汇总提示（包含审查信息）
        review_section = ""
        if task.review_result and task.review_result != "（无审查者，自动通过）":
            review_section = f"""
## 审查意见（{task.reviewer_id}）
{task.review_result[:1000]}
审查结论: {'通过' if task.review_passed else '修订后通过'}
{'修订次数: ' + str(task.retry_count) if task.retry_count > 0 else ''}
"""

        summary_prompt = f"""【协作任务 - 汇总阶段】

你是协作团队的汇总者。以下是一个协作任务的完整过程，请你：
1. 整合规划和执行的结果
2. 检查是否有遗漏或需要补充的地方
3. 输出一份清晰、完整的最终答案

## 原始任务
{task.original_text}

## 规划师（{task.planner_id}）的分析
{task.plan_result[:2000]}

## 执行者（Claude Opus 4.6）的结果
{task.exec_result[:4000]}
{review_section}
---
请输出最终的汇总结果。格式要求：
- 开头简要说明协作过程
- 然后给出完整的最终答案
- 如有必要，补充规划和执行中遗漏的内容"""

        try:
            result = await summarizer(task.chat_id, summary_prompt)
            task.summary_result = result
            task.phase = CollabPhase.DONE
            logger.info(f"[Collab] {task.task_id} 汇总完成 by {task.summarizer_id}")
            return result
        except Exception as e:
            task.error = f"汇总失败: {e}"
            logger.error(f"[Collab] {task.task_id} 汇总失败: {e}")
            return task.error

    async def run_full_pipeline(self, task: CollabTask) -> CollabTask:
        """运行完整的协作流程（含审查循环）"""
        await self.run_planning(task)
        if task.error:
            return task

        await self.run_execution(task)
        if task.error:
            return task

        # 审查循环
        await self.run_review(task)
        while not task.review_passed and task.retry_count < task.max_retries:
            await self.run_revised_execution(task)
            if task.error:
                return task
            await self.run_review(task)

        await self.run_summary(task)
        return task

    def get_active_task(self, chat_id: int) -> Optional[CollabTask]:
        """获取某个 chat 的活跃协作任务"""
        for task in self.active_tasks.values():
            if task.chat_id == chat_id and task.phase != CollabPhase.DONE:
                return task
        return None

    def cleanup_old_tasks(self, max_age: float = 3600.0):
        """清理超时的协作任务"""
        now = time.time()
        expired = [
            tid for tid, task in self.active_tasks.items()
            if now - task.created_at > max_age
        ]
        for tid in expired:
            del self.active_tasks[tid]
