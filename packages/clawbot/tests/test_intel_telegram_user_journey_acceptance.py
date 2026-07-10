from __future__ import annotations

import json


def test_user_journey_acceptance_verifies_menu_to_pause_resume_flow(tmp_path):
    from scripts.intel_telegram_user_journey_acceptance import build_user_journey_acceptance

    output = tmp_path / "journey.json"
    db_path = tmp_path / "journey.sqlite3"
    report = build_user_journey_acceptance(db_path=db_path, output_path=output)

    assert report["verified"] is True
    assert report["status"] == "verified"
    assert report["summary"] == {
        "total_steps": 14,
        "passed_steps": 14,
        "failed_steps": 0,
        "final_subscription_status": "active",
        "final_frequency": "weekly",
        "final_delivery_time": "09:00",
        "final_enabled_categories": [
            "ai_model_updates",
            "air_quality",
            "akshare",
            "disaster_alerts",
            "github_trending",
            "humidity",
            "institutional_13f",
            "rainfall",
            "senate_trading",
            "temperature",
            "weather",
        ],
    }
    assert [step["step"] for step in report["steps"]] == [
        "打开菜单 /start",
        "点今日简报",
        "清聊天后点左侧命令 /today",
        "点我的订阅",
        "点推送时间 /schedule → 回复 2",
        "数字备用 705 → 回复 每周 09:00",
        "左侧命令 /market /ai /weather",
        "添加追踪 706 英伟达",
        "两步式添加追踪 706→周杰伦",
        "左侧命令 /track → OpenEverything",
        "暂停简报 708",
        "暂停后查看状态 701",
        "暂停后打开菜单 /start",
        "选择市场资金 702 恢复",
    ]
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["redaction"]["uses_sandbox_db_only"] is True
    assert saved["redaction"]["real_telegram_network_calls"] == 0
    assert "journey-chat" not in output.read_text(encoding="utf-8")
    assert db_path.exists()


def test_user_journey_acceptance_cli_writes_report(tmp_path):
    from scripts.intel_telegram_user_journey_acceptance import main

    output = tmp_path / "journey-cli.json"
    db_path = tmp_path / "journey-cli.sqlite3"

    exit_code = main(["--db", str(db_path), "--output", str(output)])

    assert exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["verified"] is True
    assert saved["summary"]["failed_steps"] == 0
