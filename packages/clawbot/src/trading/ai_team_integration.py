"""
Trading — AI 团队集成
AI 团队投票的注入点和包装器
"""
import logging
from typing import Dict, Callable, Optional

logger = logging.getLogger(__name__)

# 全局 AI 团队 API callers（由 multi_main.py 注入）
_ai_team_api_callers: Dict[str, Callable] = {}


def set_ai_team_callers(callers: dict):
    """注入 AI 团队的 API 调用函数（在 bot 启动后调用）"""
    global _ai_team_api_callers
    _ai_team_api_callers = callers
    logger.info("[Trading.AITeam] callers 已注入: %s", list(callers.keys()))


def get_ai_team_callers() -> Dict[str, Callable]:
    return _ai_team_api_callers


async def ai_team_wrapper(
    candidates: list,
    run_team_vote_batch_fn: Callable,
    notify_fn: Optional[Callable] = None,
    **kwargs,
) -> Optional[dict]:
    """
    AI 团队投票包装器。
    将候选标的提交给 AI 团队进行多模型投票。
    """
    if not candidates:
        return None
    if not _ai_team_api_callers:
        logger.warning("[Trading.AITeam] 无可用 callers，跳过投票")
        return None
    try:
        result = await run_team_vote_batch_fn(
            candidates=candidates,
            api_callers=_ai_team_api_callers,
            notify_fn=notify_fn,
            **kwargs,
        )
        return result
    except Exception as e:
        logger.error(f"[Trading.AITeam] 投票失败: {e}")
        return None
