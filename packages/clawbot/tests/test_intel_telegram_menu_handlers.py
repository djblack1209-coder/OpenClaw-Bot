from __future__ import annotations

import sqlite3

from src.intel.subscriptions import grant_subscription, upsert_subscription_plan

NOW = "2026-07-07T16:00:00+00:00"


def test_start_creates_telegram_subscriber_and_returns_menu_without_network(tmp_path):
    from src.intel.subscriptions import get_subscription_profile
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu.db"
    user = TelegramUserContext(telegram_user_id="sandbox-user", chat_id="sandbox-chat", username="tester")

    result = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    assert result["status"] == "success"
    assert result["command"] == "start"
    assert result["network_calls"] == 0
    assert result["redacted_user"] == {"telegram_user_id_present": True, "chat_id_present": True}
    assert "CARVEN 情报简报" in result["reply_text"]
    assert "700 今日简报" in result["reply_text"]
    assert "706 添加追踪" in result["reply_text"]
    assert "inactive_or_expired" not in result["reply_text"]
    assert result["prelude_replies"][0]["reply_markup"]["keyboard"] == [
        [{"text": "🧭 今日简报"}, {"text": "📌 我的订阅"}]
    ]
    assert [item["command"] for item in result["menu"]["commands"]] == [
        "start",
        "today",
        "status",
        "market",
        "ai",
        "weather",
        "schedule",
        "track",
        "pause",
        "help",
    ]
    assert [item["description"] for item in result["menu"]["commands"]] == [
        "打开菜单",
        "今日简报",
        "我的订阅",
        "市场资金",
        "AI科技",
        "天气预警",
        "推送时间",
        "添加追踪",
        "暂停简报",
        "帮助",
    ]

    profile = get_subscription_profile(db_path, user_id="tg:sandbox-user", now=NOW)
    assert profile["status"] == "inactive_or_expired"
    assert profile["channel_type"] == "telegram"
    assert profile["channel_user_id"] == "sandbox-chat"


def test_sources_schedule_and_status_commands_update_active_profile(tmp_path):
    from src.intel.subscriptions import get_subscription_profile
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu.db"
    user = TelegramUserContext(telegram_user_id="active-user", chat_id="active-chat")
    start = handle_intel_telegram_command(db_path, user=user, command="start", args=[], now=NOW)
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant_subscription(
        db_path,
        user_id=start["subscriber"]["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="manual_contract_test",
    )

    sources = handle_intel_telegram_command(
        db_path,
        user=user,
        command="/sources",
        args=["senate_trading", "akshare", "akshare"],
        now=NOW,
    )
    schedule = handle_intel_telegram_command(
        db_path,
        user=user,
        command="/schedule",
        args=["daily", "08:30", "America/Denver"],
        now=NOW,
    )
    status = handle_intel_telegram_command(db_path, user=user, command="/status", args=[], now=NOW)

    assert sources["status"] == "success"
    assert sources["enabled_categories"] == ["akshare", "senate_trading"]
    assert "A股资金流向、国会持仓" in sources["reply_text"]
    assert "akshare" not in sources["reply_text"]
    assert schedule["delivery_preferences"] == {
        "frequency": "daily",
        "delivery_time": "08:30",
        "timezone": "America/Denver",
    }
    assert "08:30" in schedule["reply_text"]
    assert status["subscription_status"] == "active"
    assert "intel_mvp_monthly" in status["reply_text"]
    assert "已启用分类：A股资金流向、国会持仓" in status["reply_text"]
    assert "senate_trading" not in status["reply_text"]
    assert status["network_calls"] == 0

    profile = get_subscription_profile(db_path, user_id="tg:active-user", now=NOW)
    assert profile["eligible"] is True
    assert profile["enabled_categories"] == ["akshare", "senate_trading"]
    assert profile["delivery_preferences"]["timezone"] == "America/Denver"


def test_schedule_accepts_time_only_argument_like_a_normal_user(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_schedule_time_only.db"
    user = TelegramUserContext(telegram_user_id="schedule-user", chat_id="schedule-chat")
    handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    result = handle_intel_telegram_command(db_path, user=user, command="/schedule", args=["09:00"], now=NOW)

    assert result["status"] == "success"
    assert result["command"] == "schedule"
    assert result["delivery_preferences"] == {
        "frequency": "daily",
        "delivery_time": "09:00",
        "timezone": "America/Denver",
    }
    assert "09:00" in result["reply_text"]


def test_slash_menu_aliases_match_numbered_menu_for_users_after_chat_cleanup(tmp_path):
    from src.intel.subscriptions import get_subscription_profile
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_slash_aliases.db"
    user = TelegramUserContext(telegram_user_id="slash-user", chat_id="slash-chat")
    start = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant_subscription(
        db_path,
        user_id=start["subscriber"]["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="slash_alias_test",
    )

    today = handle_intel_telegram_command(db_path, user=user, command="/today", args=[], now=NOW)
    market = handle_intel_telegram_command(db_path, user=user, command="/market", args=[], now=NOW)
    ai = handle_intel_telegram_command(db_path, user=user, command="/ai", args=[], now=NOW)
    weather = handle_intel_telegram_command(db_path, user=user, command="/weather", args=[], now=NOW)
    track_prompt = handle_intel_telegram_command(db_path, user=user, command="/track", args=[], now=NOW)
    track = handle_intel_telegram_command(db_path, user=user, command="/track", args=["英伟达"], now=NOW)
    pause = handle_intel_telegram_command(db_path, user=user, command="/pause", args=[], now=NOW)
    status_after_pause = get_subscription_profile(db_path, user_id=start["subscriber"]["user_id"], now=NOW)

    assert today["command"] == "today"
    assert "今日简报" in today["reply_text"]
    assert market["enabled_categories"] == ["akshare", "institutional_13f", "senate_trading"]
    assert ai["enabled_categories"] == ["ai_model_updates", "github_trending"]
    assert weather["enabled_categories"] == ["air_quality", "disaster_alerts", "humidity", "rainfall", "temperature", "weather"]
    assert track_prompt["status"] == "prompt"
    assert "下一条直接回复名字" in track_prompt["reply_text"]
    assert track["status"] == "success"
    assert "英伟达" in track["reply_text"]
    assert pause["command"] == "pause"
    assert status_after_pause["status"] == "paused"


def test_schedule_two_step_flow_accepts_number_and_plain_language_frequency(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_schedule_two_step.db"
    user = TelegramUserContext(telegram_user_id="schedule-two-step-user", chat_id="schedule-two-step-chat")
    handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    prompt = handle_intel_telegram_command(db_path, user=user, command="705", args=[], now=NOW)
    quick_choice = handle_intel_telegram_command(db_path, user=user, command="2", args=[], now=NOW)
    prompt_again = handle_intel_telegram_command(db_path, user=user, command="/schedule", args=[], now=NOW)
    weekly = handle_intel_telegram_command(db_path, user=user, command="每周 09:00", args=[], now=NOW)

    assert prompt["status"] == "prompt"
    assert "回复数字即可设置" in prompt["reply_text"]
    assert quick_choice["status"] == "success"
    assert quick_choice["delivery_preferences"]["frequency"] == "daily"
    assert quick_choice["delivery_preferences"]["delivery_time"] == "09:00"
    assert prompt_again["status"] == "prompt"
    assert weekly["delivery_preferences"]["frequency"] == "weekly"
    assert weekly["delivery_preferences"]["delivery_time"] == "09:00"


def test_today_shortcut_returns_latest_brief_instead_of_reopening_menu(tmp_path):
    import sqlite3

    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_today_shortcut.db"
    user = TelegramUserContext(telegram_user_id="today-user", chat_id="today-chat")
    start = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)
    subscriber_id = int(start["subscriber"]["subscriber_id"])
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, delivered_at, content_summary, channel_type, success)
            VALUES (?, '2026-07-08T08:30:00+00:00', '今日真实摘要：A股资金流和AI模型动态。', 'telegram', 1)
            """,
            (subscriber_id,),
        )
        conn.commit()

    today = handle_intel_telegram_command(db_path, user=user, command="🧭 今日简报", args=[], now=NOW)
    status = handle_intel_telegram_command(db_path, user=user, command="📌 我的订阅", args=[], now=NOW)

    assert today["status"] == "success"
    assert today["command"] == "today"
    assert "今日真实摘要" in today["reply_text"]
    assert "CARVEN 情报简报" not in today["reply_text"]
    assert status["status"] == "success"
    assert status["command"] == "status"
    assert "订阅状态" in status["reply_text"]


def test_today_shortcut_does_not_duplicate_new_brief_heading(tmp_path):
    import sqlite3

    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_today_heading.db"
    user = TelegramUserContext(telegram_user_id="today-heading-user", chat_id="today-heading-chat")
    start = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)
    subscriber_id = int(start["subscriber"]["subscriber_id"])
    content = "🧭 今日情报简报\n7月10日 · 为你精选 2 条\n\n今日重点\nA股资金和 AI 动态。"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, delivered_at, content_summary, channel_type, success)
            VALUES (?, '2026-07-10T08:30:00+00:00', ?, 'telegram', 1)
            """,
            (subscriber_id, content),
        )
        conn.commit()

    today = handle_intel_telegram_command(db_path, user=user, command="🧭 今日简报", args=[], now=NOW)

    assert today["reply_text"] == content
    assert today["reply_text"].count("🧭") == 1


def test_pause_is_not_silently_cancelled_by_status_or_menu(tmp_path):
    from src.intel.subscriptions import get_subscription_profile
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_pause.db"
    user = TelegramUserContext(telegram_user_id="pause-user", chat_id="pause-chat")
    start = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant_subscription(
        db_path,
        user_id=start["subscriber"]["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="pause_test",
    )

    pause = handle_intel_telegram_command(db_path, user=user, command="708", args=[], now=NOW)
    status_after_pause = handle_intel_telegram_command(db_path, user=user, command="701", args=[], now=NOW)
    menu_after_pause = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)
    profile_after_menu = get_subscription_profile(db_path, user_id=start["subscriber"]["user_id"], now=NOW)
    resume = handle_intel_telegram_command(db_path, user=user, command="702", args=[], now=NOW)
    profile_after_resume = get_subscription_profile(db_path, user_id=start["subscriber"]["user_id"], now=NOW)

    assert pause["status"] == "success"
    assert pause["command"] == "pause"
    assert status_after_pause["profile"]["status"] == "paused"
    assert "已暂停" in status_after_pause["reply_text"]
    assert "当前状态：已暂停" in menu_after_pause["reply_text"]
    assert profile_after_menu["status"] == "paused"
    assert resume["status"] == "success"
    assert resume["command"] == "sources"
    assert profile_after_resume["status"] == "active"


def test_custom_command_subscribes_open_tracking_target_and_writes_audit_without_scraping(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu.db"
    user = TelegramUserContext(telegram_user_id="custom-user", chat_id="custom-chat")
    handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    result = handle_intel_telegram_command(db_path, user=user, command="/custom", args=["周杰伦"], now=NOW)

    assert result["status"] == "success"
    assert result["tracking_target"] == {
        "name": "周杰伦",
        "normalized_name": "周杰伦",
        "active_subscription_count": 1,
    }
    assert result["scrape_triggered"] is False
    assert result["network_calls"] == 0
    assert "周杰伦" in result["reply_text"]

    with sqlite3.connect(db_path) as conn:
        audit_rows = conn.execute(
            "SELECT subscriber_user_id, target_name, source_channel FROM tracking_audit_log"
        ).fetchall()
    assert audit_rows == [("tg:custom-user", "周杰伦", "telegram_menu")]


def test_sandbox_evidence_builder_simulates_user_menu_flow_without_network(tmp_path):
    from scripts.intel_telegram_menu_sandbox import build_intel_telegram_menu_sandbox_evidence

    evidence_dir = tmp_path / "evidence"
    evidence = build_intel_telegram_menu_sandbox_evidence(evidence_dir, now=NOW)

    assert evidence["status"] == "success"
    assert evidence["phase"] == "Z-telegram-menu-handler-contract"
    assert evidence["network_calls"] == 0
    assert [step["command"] for step in evidence["steps"]] == ["start", "grant", "sources", "schedule", "custom", "status"]
    assert evidence["final_profile"]["status"] == "active"
    assert evidence["final_profile"]["enabled_categories"] == ["akshare", "senate_trading"]
    assert evidence["tracking_target"]["name"] == "周杰伦"
    assert evidence["button_preference_flow"] == {
        "after_stock_button": ["akshare", "institutional_13f", "senate_trading"],
        "after_github_button": ["akshare", "github_trending", "institutional_13f", "senate_trading"],
        "after_github_toggle_off": ["akshare", "institutional_13f", "senate_trading"],
    }
    assert evidence["button_preference_flow_display"] == {
        "after_stock_button": ["A股资金流向", "机构13F持仓", "国会持仓"],
        "after_github_button": ["A股资金流向", "GitHub趋势", "机构13F持仓", "国会持仓"],
        "after_github_toggle_off": ["A股资金流向", "机构13F持仓", "国会持仓"],
    }
    assert evidence["redaction"]["chat_id_present_only"] is True
    assert (evidence_dir / "evidence.json").exists()
    assert (evidence_dir / "intel_telegram_menu_sandbox.db").exists()


def test_start_returns_inline_keyboard_card_menu_like_reference(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_inline.db"
    user = TelegramUserContext(telegram_user_id="inline-user", chat_id="inline-chat")

    result = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    markup = result["reply_markup"]
    assert "keyboard" not in markup
    keyboard = markup["inline_keyboard"]
    assert [[button["text"] for button in row] for row in keyboard] == [
        ["🧭 今日简报", "📌 我的订阅"],
        ["📈 市场资金", "🤖 AI科技"],
        ["🌦 天气预警", "⏰ 推送时间"],
        ["➕ 添加追踪", "❓ 帮助"],
    ]
    assert "命令：/sources" not in result["reply_text"]
    assert "订阅状态：" not in result["reply_text"]
    assert "可点击按钮，也可直接回复数字" in result["reply_text"]
    assert result["menu"]["persistent_keyboard"] == [["🧭 今日简报", "📌 我的订阅"]]
    assert result["prelude_replies"][0]["reply_markup"]["is_persistent"] is True
    assert keyboard[0][0] == {"text": "🧭 今日简报", "callback_data": "today"}
    assert keyboard[2][1] == {"text": "⏰ 推送时间", "callback_data": "schedule"}
    assert keyboard[3][0] == {"text": "➕ 添加追踪", "callback_data": "custom"}
    assert keyboard[3][1] == {"text": "❓ 帮助", "callback_data": "help"}
    assert result["menu"]["menu_style"] == "product_numbered_inline_card_with_persistent_shortcuts"


def test_native_menu_buttons_map_to_commands(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_buttons.db"

    def click(command: str, suffix: str) -> dict[str, object]:
        user = TelegramUserContext(telegram_user_id=f"button-user-{suffix}", chat_id=f"button-chat-{suffix}")
        handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)
        return handle_intel_telegram_command(db_path, user=user, command=command, args=[], now=NOW)

    github = click("Github", "github")
    openai = click("openai", "openai")
    claude = click("claude", "claude")
    deepseek = click("deepseek", "deepseek")
    custom = click("custom", "custom")
    schedule = click("schedule", "schedule")
    settings = click("settings", "settings")
    search = click("search", "search")
    market = click("market", "market")
    ai_tech = click("ai_tech", "ai-tech")
    weather_alerts = click("weather_alerts", "weather-alerts")
    hot = click("🔥 热搜排行", "hot")
    nav = click("👥 功能导航", "nav")

    assert github["status"] == "success"
    assert github["command"] == "sources"
    assert github["enabled_categories"] == ["github_trending"]
    assert "GitHub趋势" in github["reply_text"]
    assert "github_trending" not in github["reply_text"]
    assert openai["enabled_categories"] == ["ai_model_updates"]
    assert claude["enabled_categories"] == ["ai_model_updates"]
    assert deepseek["enabled_categories"] == ["ai_model_updates"]
    assert custom["status"] == "prompt"
    assert custom["command"] == "custom"
    assert "706 周杰伦" in custom["reply_text"]
    assert schedule["status"] == "prompt"
    assert schedule["command"] == "schedule"
    assert "回复数字即可设置" in schedule["reply_text"]
    assert settings["status"] == "success"
    assert settings["command"] == "status"
    assert search["status"] == "prompt"
    assert search["command"] == "search"
    assert "直接发送关键词" in search["reply_text"]
    assert market["enabled_categories"] == ["akshare", "institutional_13f", "senate_trading"]
    assert ai_tech["enabled_categories"] == ["ai_model_updates", "github_trending"]
    assert weather_alerts["enabled_categories"] == ["air_quality", "disaster_alerts", "humidity", "rainfall", "temperature", "weather"]
    assert hot["command"] == "start"
    assert hot["reply_markup"]["inline_keyboard"][0][0]["text"] == "🧭 今日简报"
    assert nav["command"] == "start"
    assert nav["reply_markup"]["inline_keyboard"][0][0]["text"] == "🧭 今日简报"



def test_706_prompt_accepts_next_plain_keyword_as_tracking_target(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_pending_custom.db"
    user = TelegramUserContext(telegram_user_id="pending-custom-user", chat_id="pending-custom-chat")
    handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    prompt = handle_intel_telegram_command(db_path, user=user, command="706", args=[], now=NOW)
    follow_up = handle_intel_telegram_command(db_path, user=user, command="英伟达", args=[], now=NOW)
    normal_keyword_after_consumed = handle_intel_telegram_command(db_path, user=user, command="黄仁勋", args=[], now=NOW)

    assert prompt["status"] == "prompt"
    assert prompt["command"] == "custom"
    assert "下一条直接回复" in prompt["reply_text"]
    assert follow_up["status"] == "success"
    assert follow_up["command"] == "custom"
    assert follow_up["tracking_target"]["name"] == "英伟达"
    assert "已添加追踪：英伟达" in follow_up["reply_text"]
    assert normal_keyword_after_consumed["status"] == "prompt"
    assert normal_keyword_after_consumed["command"] == "黄仁勋"
    assert "已收到关键词：黄仁勋" in normal_keyword_after_consumed["reply_text"]

def test_plain_keyword_text_is_treated_as_search_prompt(tmp_path):
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_keyword.db"
    user = TelegramUserContext(telegram_user_id="keyword-user", chat_id="keyword-chat")
    handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    result = handle_intel_telegram_command(db_path, user=user, command="英伟达财报", args=[], now=NOW)

    assert result["status"] == "prompt"
    assert result["command"] == "英伟达财报"
    assert "已收到关键词：英伟达财报" in result["reply_text"]


def test_category_buttons_append_to_existing_preferences_without_overwriting(tmp_path):
    from src.intel.subscriptions import get_subscription_profile
    from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command

    db_path = tmp_path / "intel_menu_button_append.db"
    user = TelegramUserContext(telegram_user_id="append-user", chat_id="append-chat")
    handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=NOW)

    stock = handle_intel_telegram_command(db_path, user=user, command="股市", args=[], now=NOW)
    github = handle_intel_telegram_command(db_path, user=user, command="Github", args=[], now=NOW)
    github_again = handle_intel_telegram_command(db_path, user=user, command="Github", args=[], now=NOW)

    assert stock["status"] == "success"
    assert stock["enabled_categories"] == ["akshare", "institutional_13f", "senate_trading"]
    assert github["status"] == "success"
    assert github["enabled_categories"] == ["akshare", "github_trending", "institutional_13f", "senate_trading"]
    assert github_again["status"] == "success"
    assert github_again["enabled_categories"] == ["akshare", "institutional_13f", "senate_trading"]

    profile = get_subscription_profile(db_path, user_id="tg:append-user", now=NOW)
    assert profile["enabled_categories"] == ["akshare", "institutional_13f", "senate_trading"]


def test_inline_callback_button_maps_to_sources_command(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    class FakeSender:
        def __init__(self) -> None:
            self.sent = []
            self.callback_answers = []
            self.network_calls = 0

        def send(self, chat_id: str, text: str, *, parse_mode: str = "HTML", reply_markup=None):
            self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {
                "success": True,
                "network": "fake_sender",
                "network_calls": 0,
                "chat_id_present": bool(chat_id),
                "message_id": f"fake-{len(self.sent)}",
                "endpoint": "fake://telegram/sendMessage",
                "reply_markup_present": bool(reply_markup),
            }

        def answer_callback_query(self, callback_query_id: str, *, text: str = ""):
            self.callback_answers.append({"callback_query_id": callback_query_id, "text": text})
            return {
                "success": True,
                "network": "fake_sender",
                "network_calls": 0,
                "callback_query_id_present": bool(callback_query_id),
                "error_present": False,
            }

    db_path = tmp_path / "inline_callback.db"
    sender = FakeSender()
    update = {
        "update_id": 10,
        "callback_query": {
            "id": "callback-1",
            "data": "market",
            "from": {"id": "callback-user", "username": "tester"},
            "message": {"message_id": 9, "chat": {"id": "callback-chat", "type": "private"}},
        },
    }

    result = process_intel_telegram_updates(db_path, updates=[update], sender=sender, now=NOW)

    assert result["status"] == "success"
    assert result["handled_updates"][0]["message_key"] == "callback_query"
    assert result["handled_updates"][0]["callback_query_id_present"] is True
    assert result["handled_updates"][0]["callback_answer_success"] is True
    assert result["handled_updates"][0]["command"] == "sources"
    assert "A股资金流向" in sender.sent[0]["text"]
    assert "senate_trading" not in sender.sent[0]["text"]
    assert sender.callback_answers == [{"callback_query_id": "callback-1", "text": "已收到"}]
