"""
e2e 测试 — 生活自动化路径（记账 + 提醒）

覆盖场景:
  1. 中文 NLP 匹配: 记账触发词（花了50吃午饭）、月度汇总（这个月花了多少）
  2. 中文 NLP 匹配: 提醒触发词（提醒我明天开会）、闹钟同义词（设个闹钟下午3点）
  3. 记账功能: add_expense 返回确认、get_monthly_summary 包含新增记录
  4. 提醒功能: create_reminder 返回确认、list_reminders 包含新建提醒
"""

import os
import sys
import tempfile

import pytest

# 确保 src/ 可直接 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.bot.chinese_nlp_mixin import _match_chinese_command
from src.execution._db import init_db
from src.execution.bookkeeping import add_expense, get_monthly_summary
from src.execution.life_automation import create_reminder, list_reminders


# ============================================================================
# 辅助 fixture: 临时数据库（每个测试用例隔离）
# ============================================================================


@pytest.fixture
def tmp_db():
    """创建临时 SQLite 数据库，自动初始化表结构，测试结束后清理。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_life.db")
        init_db(db_path)
        yield db_path


# ============================================================================
# 测试类 1: 记账相关的 NLP 匹配
# ============================================================================


class TestExpenseNLPMatch:
    """验证中文记账触发词能被正确匹配为对应的 action_type。"""

    def test_expense_add(self):
        """'花了50吃午饭' 应匹配为 expense_add 类型，金额50、备注午饭"""
        result = _match_chinese_command("花了50吃午饭")
        assert result is not None, "NLP 未能匹配 '花了50吃午饭'"
        action_type, arg = result
        assert action_type == "expense_add", f"期望 expense_add，实际 {action_type}"
        # arg 格式: "50|||午饭"
        assert "50" in arg, f"参数中应包含金额 50，实际: {arg}"
        assert "午饭" in arg, f"参数中应包含备注 '午饭'，实际: {arg}"

    def test_expense_summary(self):
        """'这个月花了多少' 应匹配为 monthly_summary 类型"""
        result = _match_chinese_command("这个月花了多少")
        assert result is not None, "NLP 未能匹配 '这个月花了多少'"
        action_type, _ = result
        assert action_type == "monthly_summary", f"期望 monthly_summary，实际 {action_type}"


# ============================================================================
# 测试类 2: 提醒相关的 NLP 匹配
# ============================================================================


class TestReminderNLPMatch:
    """验证中文提醒触发词能被正确匹配为对应的 action_type。"""

    def test_remind_command(self):
        """'提醒我 明天开会' 应匹配为 ops_life_remind 类型
        注意: NLP 正则要求 '提醒我' 后跟空格再接内容，这与 Telegram 用户输入习惯一致。
        """
        result = _match_chinese_command("提醒我 明天开会")
        assert result is not None, "NLP 未能匹配 '提醒我 明天开会'"
        action_type, arg = result
        assert action_type == "ops_life_remind", f"期望 ops_life_remind，实际 {action_type}"
        # 参数应包含"开会"内容
        assert "开会" in arg, f"参数中应包含提醒内容 '开会'，实际: {arg}"

    def test_alarm_synonym(self):
        """'设个闹钟下午3点' 应匹配为 ops_life_remind（闹钟是提醒的同义词）"""
        result = _match_chinese_command("设个闹钟下午3点")
        assert result is not None, "NLP 未能匹配 '设个闹钟下午3点'"
        action_type, arg = result
        assert action_type == "ops_life_remind", f"期望 ops_life_remind，实际 {action_type}"


# ============================================================================
# 测试类 3: 记账数据库操作
# ============================================================================


class TestExpenseBookkeeping:
    """验证记账函数的数据库读写正确性（使用临时数据库隔离）。"""

    def test_add_expense_returns_confirmation(self, tmp_db):
        """add_expense 应返回包含 success=True 和正确金额的确认字典"""
        result = add_expense(
            user_id=12345,
            amount=50.0,
            note="午饭",
            db_path=tmp_db,
        )
        assert isinstance(result, dict), f"返回值应为 dict，实际: {type(result)}"
        assert result.get("success") is True, f"记账应成功，实际: {result}"
        assert result.get("amount") == 50.0, f"金额应为 50.0，实际: {result.get('amount')}"

    def test_monthly_summary_after_expense(self, tmp_db):
        """记一笔账后，月度汇总应包含这笔支出"""
        # 先记一笔
        add_expense(user_id=12345, amount=88.5, note="晚饭", db_path=tmp_db)

        # 查月度汇总
        summary = get_monthly_summary(user_id=12345, db_path=tmp_db)
        assert summary.get("success") is True, f"月度汇总查询应成功，实际: {summary}"
        total = summary.get("total_expense", 0)
        assert total >= 88.5, f"月度总支出应 >= 88.5，实际: {total}"


# ============================================================================
# 测试类 4: 提醒数据库操作
# ============================================================================


class TestReminderCreation:
    """验证提醒函数的数据库读写正确性（使用临时数据库隔离）。"""

    @pytest.mark.asyncio
    async def test_create_reminder_returns_confirmation(self, tmp_db):
        """create_reminder 应返回包含 success=True 和提醒内容的确认字典"""
        result = await create_reminder(
            message="明天开会",
            delay_minutes=30,
            db_path=tmp_db,
        )
        assert isinstance(result, dict), f"返回值应为 dict，实际: {type(result)}"
        assert result.get("success") is True, f"创建提醒应成功，实际: {result}"
        assert result.get("message") == "明天开会", f"提醒内容应为 '明天开会'，实际: {result.get('message')}"
        assert result.get("reminder_id") is not None, "应返回 reminder_id"

    @pytest.mark.asyncio
    async def test_list_reminders_after_create(self, tmp_db):
        """创建提醒后，list_reminders 应能查到该提醒"""
        # 先创建一条提醒
        await create_reminder(
            message="下午交报告",
            delay_minutes=60,
            db_path=tmp_db,
        )

        # 查询待触发提醒列表
        reminders = list_reminders(status="pending", db_path=tmp_db)
        assert len(reminders) >= 1, f"应至少有 1 条提醒，实际: {len(reminders)}"

        # 验证内容匹配
        messages = [r.get("message") for r in reminders]
        assert "下午交报告" in messages, f"提醒列表中应包含 '下午交报告'，实际: {messages}"
