from __future__ import annotations

from src.intel.telegram_brief_renderer import build_brief_envelope, event_key_for_item
from src.intel.telegram_delivery import send_delivery_envelope


def _payload():
    return {
        "brief_date": "2026-08-04",
        "llm": {"summary_text": "今天为你筛出 4 条，以下是重点。"},
        "items": [
            {
                "event_key": f"evt-{index}",
                "source": source,
                "source_label": category,
                "category": category,
                "title": title,
                "summary": f"第 {index} 条完整摘要，来源和日期均可核验。",
                "source_url": f"https://example.com/{index}?a=1&b=2",
                "published_at": f"2026-08-04T0{index}:00:00+00:00",
                "rank_score": score,
            }
            for index, (source, category, title, score) in enumerate(
                [
                    ("openai", "AI", "模型能力更新 <verified>", 92),
                    ("akshare", "市场", "深科技机构净买入", 88),
                    ("github", "趋势", "Agent toolkit trending", 81),
                    ("weather", "天气", "空气质量稳定", 55),
                ],
                1,
            )
        ],
    }


class FakeEnvelopeSender:
    def __init__(self, *, photo_result=None, photo_results=None, text_result=None, rich_result=None):
        self.network_calls = 0
        self.calls = []
        self.photo_result = photo_result or {"success": True, "message_id": "p1", "photo_file_id": "file-1"}
        self.photo_results = list(photo_results or [])
        self.text_result = text_result or {"success": True, "message_id": "t1"}
        self.rich_result = rich_result or {"success": True, "message_id": "r1"}

    def send_photo(self, chat_id, photo, **kwargs):
        self.network_calls += 1
        self.calls.append("photo")
        if self.photo_results:
            return dict(self.photo_results.pop(0))
        return dict(self.photo_result)

    def send(self, chat_id, text, **kwargs):
        self.network_calls += 1
        self.calls.append("text")
        return dict(self.text_result)

    def send_rich_message(self, chat_id, envelope, **kwargs):
        self.network_calls += 1
        self.calls.append("rich")
        return dict(self.rich_result)


def test_renderer_keeps_top_three_in_caption_and_full_replay():
    envelope = build_brief_envelope(_payload(), brief_ref="abc123", language="zh", cover_path="")

    assert len(envelope.caption_html) < 1024
    assert "模型能力更新 &lt;verified&gt;" in envelope.caption_html
    assert "空气质量稳定" not in envelope.caption_html
    assert "空气质量稳定" in envelope.full_text_html
    assert envelope.item_event_keys == ["evt-1", "evt-2", "evt-3", "evt-4"]
    callback_values = [button["callback_data"] for row in envelope.reply_markup["inline_keyboard"] for button in row]
    assert callback_values == [
        "ib1:v:market:abc123",
        "ib1:v:ai:abc123",
        "ib1:v:all:abc123",
        "ib1:l:en:abc123",
    ]
    assert event_key_for_item({"source": "a", "title": "b"}) == event_key_for_item({"source": "a", "title": "b"})


def test_renderer_preserves_pipeline_diversity_rank_over_raw_score():
    payload = _payload()
    payload["items"] = [
        {
            "event_key": "market-1",
            "source": "akshare",
            "category": "market",
            "title": "市场第一条",
            "rank_score": 100,
            "rank_position": 1,
        },
        {
            "event_key": "ai-1",
            "source": "ai_model_updates",
            "category": "ai",
            "title": "AI 第一条",
            "rank_score": 90,
            "rank_position": 2,
        },
        {
            "event_key": "tech-1",
            "source": "github_trending",
            "category": "technology",
            "title": "科技第一条",
            "rank_score": 80,
            "rank_position": 3,
        },
        {
            "event_key": "market-2",
            "source": "senate_trading",
            "category": "market",
            "title": "市场第二条高分",
            "rank_score": 99,
            "rank_position": 4,
        },
    ]

    envelope = build_brief_envelope(payload, brief_ref="ranked", language="zh", cover_path="")

    assert "市场第一条" in envelope.caption_html
    assert "AI 第一条" in envelope.caption_html
    assert "科技第一条" in envelope.caption_html
    assert "市场第二条高分" not in envelope.caption_html
    assert "市场第二条高分" in envelope.full_text_html


def test_photo_success_is_single_network_call():
    sender = FakeEnvelopeSender()
    envelope = build_brief_envelope(_payload(), brief_ref="abc123")

    result = send_delivery_envelope(sender, chat_id="private", envelope=envelope, photo="file-id")

    assert result["success"] is True
    assert result["render_mode"] == "photo"
    assert result["network_calls"] == 1
    assert sender.calls == ["photo"]


def test_explicit_photo_error_falls_back_to_text():
    sender = FakeEnvelopeSender(photo_result={"success": False, "error_code": 400, "error": "bad photo"})
    envelope = build_brief_envelope(_payload(), brief_ref="abc123", cover_path="cover.jpg")

    result = send_delivery_envelope(sender, chat_id="private", envelope=envelope, photo="bad-file")

    assert result["success"] is True
    assert result["render_mode"] == "text"
    assert sender.calls == ["photo", "text"]


def test_invalid_cached_file_id_reuploads_local_cover_once():
    sender = FakeEnvelopeSender(
        photo_results=[
            {"success": False, "error_code": 400, "error": "Bad Request: wrong file identifier specified"},
            {
                "success": True,
                "message_id": "p2",
                "photo_file_id": "fresh-file-id",
                "photo_file_unique_id": "fresh-unique-id",
            },
        ]
    )
    envelope = build_brief_envelope(_payload(), brief_ref="abc123")

    result = send_delivery_envelope(sender, chat_id="private", envelope=envelope, photo="stale-file-id")

    assert result["success"] is True
    assert result["render_mode"] == "photo"
    assert result["photo_reference_invalid"] is True
    assert result["photo_file_id"] == "fresh-file-id"
    assert result["network_calls"] == 2
    assert sender.calls == ["photo", "photo"]


def test_ambiguous_photo_error_does_not_duplicate_with_text():
    sender = FakeEnvelopeSender(photo_result={"success": False, "error": "timeout", "ambiguous_delivery": True})
    envelope = build_brief_envelope(_payload(), brief_ref="abc123", cover_path="cover.jpg")

    result = send_delivery_envelope(sender, chat_id="private", envelope=envelope, photo="file-id")

    assert result["success"] is False
    assert result["delivery_state"] == "unknown"
    assert sender.calls == ["photo"]


def test_rich_method_unsupported_falls_back_to_photo():
    sender = FakeEnvelopeSender(rich_result={"success": False, "error_code": 404, "error": "method not found"})
    envelope = build_brief_envelope(_payload(), brief_ref="abc123", cover_path="cover.jpg")

    result = send_delivery_envelope(
        sender,
        chat_id="private",
        envelope=envelope,
        photo="file-id",
        prefer_rich=True,
    )

    assert result["success"] is True
    assert result["render_mode"] == "photo"
    assert sender.calls == ["rich", "photo"]
