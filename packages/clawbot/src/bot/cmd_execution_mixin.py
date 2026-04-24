"""
Bot — 执行场景命令入口 (兼容性垫片)
从 v6.0 开始，执行场景命令已拆分为 5 个独立 Mixin:
  - cmd_social_mixin.py    社媒发布/热点/人设/日历
  - cmd_xianyu_mixin.py    闲鱼客服/风格/报表/发货
  - cmd_life_mixin.py      账单/比价/生活自动化/赏金
  - cmd_novel_mixin.py     AI小说工坊
  - cmd_ops_mixin.py       运维中枢/邮件/会议/任务

> 最后更新: 2026-03-28
"""
from src.bot.cmd_life_mixin import LifeCommandsMixin
from src.bot.cmd_novel_mixin import NovelCommandsMixin
from src.bot.cmd_ops_mixin import OpsCommandsMixin
from src.bot.cmd_social_mixin import SocialCommandsMixin
from src.bot.cmd_xianyu_mixin import XianyuCommandsMixin


class ExecutionCommandsMixin(
    SocialCommandsMixin,
    XianyuCommandsMixin,
    LifeCommandsMixin,
    NovelCommandsMixin,
    OpsCommandsMixin,
):
    """执行场景命令聚合类 — 保持 multi_bot.py 继承链不变。"""
    pass
