from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from src.intel.subscriptions import (
    grant_subscription,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)

NOW = "2026-07-07T18:00:00+00:00"


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.network_calls = 0

    def send(self, chat_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, object]:
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return {
            "success": True,
            "network": "fake_sender",
            "network_calls": 0,
            "chat_id_present": bool(chat_id),
            "message_id": f"fake-{len(self.sent)}",
            "endpoint": "fake://telegram/sendMessage",
        }


class BlockingSender:
    """让首个外发停在网络边界，稳定复现并发抢占窗口。"""

    def __init__(self) -> None:
        self.calls = 0
        self.network_calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup=None,
    ) -> dict[str, object]:
        del chat_id, text, parse_mode, reply_markup
        with self._lock:
            self.calls += 1
            self.network_calls += 1
            message_id = str(self.calls)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("测试未释放外发")
        return {
            "success": True,
            "network_calls": 1,
            "message_id": message_id,
        }


def _summary_payload() -> dict[str, object]:
    return {
        "status": "success",
        "llm": {
            "summary_text": "国会持仓与 A 股资金流摘要。",
            "model_family": "intel_local",
            "usage": {"total_tokens": 128},
        },
        "items": [
            {"source": "senate_trading", "source_label": "国会持仓", "title": "Senator Sale BYND"},
            {"source": "akshare", "source_label": "A股龙虎榜", "title": "深科技机构买入"},
            {"source": "ai_model_updates", "source_label": "AI模型动态", "title": "OpenAI frontier update"},
        ],
    }


def _seed_user(
    db_path, tg_user_id: str, chat_id: str, categories: list[str], *, expires_at: str = "2026-08-07T00:00:00+00:00"
):
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id=tg_user_id, chat_id=chat_id)
    grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at=expires_at,
        source="delivery_contract_test",
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=categories)
    return subscriber


def test_subscription_filtered_delivery_sends_only_to_matching_active_preferences(tmp_path):
    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers

    db_path = tmp_path / "intel_delivery.db"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["senate_trading", "akshare"])
    _seed_user(db_path, "akshare-user", "chat-akshare", ["akshare"])
    _seed_user(db_path, "senate-user", "chat-senate", ["senate_trading"])
    _seed_user(db_path, "ai-user", "chat-ai", ["ai_model_updates"])
    _seed_user(db_path, "expired-user", "chat-expired", ["akshare"], expires_at="2026-07-01T00:00:00+00:00")
    sender = FakeSender()

    result = deliver_summary_to_eligible_subscribers(
        db_path=db_path,
        summary_evidence_path=summary_path,
        sender=sender,
        now=NOW,
    )

    assert result["status"] == "success"
    assert result["source_categories"] == ["ai_model_updates", "akshare", "senate_trading"]
    assert result["summary"] == {"eligible": 3, "sent": 3, "failed": 0}
    assert [item["chat_id"] for item in sender.sent] == ["chat-akshare", "chat-senate", "chat-ai"]
    assert "深科技机构买入" in sender.sent[0]["text"]
    assert "Senator Sale BYND" not in sender.sent[0]["text"]
    assert "OpenAI frontier update" not in sender.sent[0]["text"]
    assert "今天为你筛出 1 条" in sender.sent[0]["text"]
    assert "查看下方输入条目" not in sender.sent[0]["text"]
    assert "tokens=" not in sender.sent[0]["text"]
    assert "Senator Sale BYND" in sender.sent[1]["text"]
    assert "深科技机构买入" not in sender.sent[1]["text"]
    assert "OpenAI frontier update" not in sender.sent[1]["text"]
    assert "OpenAI frontier update" in sender.sent[2]["text"]
    assert "Senator Sale BYND" not in sender.sent[2]["text"]
    assert "深科技机构买入" not in sender.sent[2]["text"]
    public_text = json.dumps(result, ensure_ascii=False)
    assert "chat-akshare" not in public_text
    assert "chat-senate" not in public_text
    assert "chat-ai" not in public_text
    assert "tg:akshare-user" not in public_text
    assert "tg:senate-user" not in public_text
    assert "user_id" not in result["deliveries"][0]
    assert result["deliveries"][0]["user_id_present"] is True
    assert result["deliveries"][0]["matched_categories"] == ["akshare"]
    assert result["deliveries"][1]["matched_categories"] == ["senate_trading"]
    assert result["deliveries"][2]["matched_categories"] == ["ai_model_updates"]

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT channel_type, success, content_summary FROM delivery_log ORDER BY id").fetchall()
    assert len(rows) == 3
    assert all(row[0] == "telegram" and row[1] == 1 for row in rows)
    assert "OpenAI frontier update" not in rows[0][2]
    assert "Senator Sale BYND" not in rows[0][2]


def test_subscription_filtered_delivery_handles_no_eligible_recipients(tmp_path):
    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers

    db_path = tmp_path / "intel_empty_delivery.db"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")
    sender = FakeSender()

    result = deliver_summary_to_eligible_subscribers(
        db_path=db_path,
        summary_evidence_path=summary_path,
        sender=sender,
        now=NOW,
    )

    assert result["status"] == "success"
    assert result["summary"] == {"eligible": 0, "sent": 0, "failed": 0}
    assert result["message_chars"] == 0
    assert sender.sent == []


def test_subscription_delivery_concurrent_runs_send_only_once(tmp_path):
    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers

    db_path = tmp_path / "intel-concurrent-delivery.db"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare"])
    _seed_user(db_path, "concurrent-user", "chat-concurrent", ["akshare"])
    sender = BlockingSender()

    kwargs = {
        "db_path": db_path,
        "summary_evidence_path": summary_path,
        "sender": sender,
        "now": NOW,
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(deliver_summary_to_eligible_subscribers, **kwargs)
        assert sender.started.wait(timeout=5)
        second = executor.submit(deliver_summary_to_eligible_subscribers, **kwargs).result(timeout=5)
        sender.release.set()
        first = first_future.result(timeout=5)

    assert sender.calls == 1
    assert first["summary"] == {"eligible": 1, "sent": 1, "failed": 0}
    assert second["summary"] == {"eligible": 1, "sent": 0, "failed": 0}
    assert second["deliveries"][0]["status"] == "skipped_delivery_in_progress"
    with sqlite3.connect(db_path) as conn:
        claims = conn.execute(
            "SELECT state, attempt_count FROM delivery_claims WHERE brief_date=?",
            (NOW[:10],),
        ).fetchall()
    assert claims == [("sent", 1)]


def test_default_subscriber_is_due_at_singapore_delivery_time(tmp_path):
    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers
    from src.intel.subscriptions import get_subscription_profile

    db_path = tmp_path / "intel_default_timezone.db"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare"])
    subscriber = _seed_user(db_path, "sg-user", "chat-sg", ["akshare"])
    sender = FakeSender()

    result = deliver_summary_to_eligible_subscribers(
        db_path=db_path,
        summary_evidence_path=summary_path,
        sender=sender,
        now="2026-08-04T00:30:00+00:00",
        enforce_delivery_window=True,
    )

    profile = get_subscription_profile(
        db_path,
        user_id=subscriber["user_id"],
        now="2026-08-04T00:30:00+00:00",
    )
    assert result["summary"] == {"eligible": 1, "sent": 1, "failed": 0}
    assert result["schedule"]["not_due_count"] == 0
    assert profile["delivery_preferences"]["timezone"] == "Asia/Singapore"


def test_subscription_filtered_delivery_matches_weather_subcategory_aliases(tmp_path):
    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers

    db_path = tmp_path / "intel_weather_delivery.db"
    summary_path = tmp_path / "weather-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "success",
                "llm": {"summary_text": "天气摘要", "usage": {"total_tokens": 64}},
                "items": [
                    {
                        "source": "weather",
                        "category": "temperature",
                        "category_aliases": ["weather", "temperature"],
                        "source_label": "天气监测",
                        "title": "Denver, CO 温度：72°F",
                    },
                    {
                        "source": "weather",
                        "category": "air_quality",
                        "category_aliases": ["weather", "air_quality"],
                        "source_label": "天气监测",
                        "title": "Denver, CO 空气质量：US AQI 42",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    upsert_subscription_plan(
        db_path, plan_name="intel_mvp_monthly", categories=["weather", "temperature", "air_quality"]
    )
    _seed_user(db_path, "temperature-user", "chat-temperature", ["temperature"])
    _seed_user(db_path, "weather-user", "chat-weather", ["weather"])
    sender = FakeSender()

    result = deliver_summary_to_eligible_subscribers(
        db_path=db_path,
        summary_evidence_path=summary_path,
        sender=sender,
        now=NOW,
    )

    assert result["status"] == "success"
    assert result["source_categories"] == ["air_quality", "temperature", "weather"]
    assert result["summary"] == {"eligible": 2, "sent": 2, "failed": 0}
    assert "Denver, CO 温度：72°F" in sender.sent[0]["text"]
    assert "空气质量" not in sender.sent[0]["text"]
    assert "Denver, CO 温度：72°F" in sender.sent[1]["text"]
    assert "Denver, CO 空气质量：US AQI 42" in sender.sent[1]["text"]
    assert result["deliveries"][0]["matched_categories"] == ["temperature"]
    assert result["deliveries"][0]["filtered_item_count"] == 1
    assert result["deliveries"][1]["matched_categories"] == ["weather"]
    assert result["deliveries"][1]["filtered_item_count"] == 2


def test_subscription_filtered_delivery_evidence_builder_is_redacted(tmp_path):
    from src.intel.subscription_delivery import build_subscription_delivery_sandbox

    output_dir = tmp_path / "evidence"
    evidence = build_subscription_delivery_sandbox(output_dir, now=NOW)

    assert evidence["status"] == "success"
    assert evidence["phase"] == "AF-subscription-filtered-delivery-sandbox"
    assert evidence["delivery"]["summary"] == {"eligible": 3, "sent": 3, "failed": 0}
    assert evidence["delivery"]["source_categories"] == ["ai_model_updates", "akshare", "senate_trading"]
    assert evidence["network_calls"] == 0
    saved = (output_dir / "evidence.json").read_text(encoding="utf-8")
    assert "chat-akshare" not in saved
    assert "chat-senate" not in saved
    assert "tg:akshare-user" not in saved
    assert "tg:senate-user" not in saved
    assert (output_dir / "intel_subscription_delivery_sandbox.db").exists()
