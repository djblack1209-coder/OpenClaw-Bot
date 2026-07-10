import sqlite3

from src.intel.db.store import initialize_intel_db
from src.intel.quality.content_moderation import FILTER_PLACEHOLDER, moderate_content, moderate_items


def test_clean_content_passes_without_classifier():
    result = moderate_content("GitHub 项目 star 增长很快", source="github")

    assert result.allowed is True
    assert result.output_text == "GitHub 项目 star 增长很快"
    assert result.status == "allowed"
    assert result.matched_keywords == []


def test_keyword_hit_marks_pending_when_classifier_not_supplied():
    result = moderate_content("某政治事件正在发酵", source="rss")

    assert result.allowed is False
    assert result.status == "needs_review"
    assert result.output_text == FILTER_PLACEHOLDER
    assert "政治事件" in result.matched_keywords
    assert result.reason == "keyword_prefilter"


def test_classifier_sensitive_filters_content_and_logs(tmp_path):
    db_path = tmp_path / "intel_brief.db"
    initialize_intel_db(db_path)

    def classifier(text, keywords):
        assert "政治人物" in text
        assert "政治人物" in keywords
        return {"sensitive": True, "label": "political_sensitive", "confidence": 0.91}

    result = moderate_content(
        "政治人物相关爆料",
        source="weibo",
        classifier=classifier,
        db_path=db_path,
        content_id="wb-1",
    )

    assert result.allowed is False
    assert result.status == "filtered"
    assert result.output_text == FILTER_PLACEHOLDER
    assert result.classifier_label == "political_sensitive"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT source, content_id, status, matched_keywords, classifier_label FROM content_moderation_log"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "weibo"
    assert rows[0][1] == "wb-1"
    assert rows[0][2] == "filtered"
    assert "政治人物" in rows[0][3]
    assert rows[0][4] == "political_sensitive"


def test_moderate_items_replaces_only_filtered_text():
    def classifier(_text, _keywords):
        return True

    items = [
        {"id": "1", "source": "rss", "title": "OpenAI 发布模型更新"},
        {"id": "2", "source": "rss", "title": "政治事件相关内容"},
    ]

    moderated = moderate_items(items, classifier=classifier)

    assert moderated[0]["title"] == "OpenAI 发布模型更新"
    assert moderated[0]["moderation_status"] == "allowed"
    assert moderated[1]["title"] == FILTER_PLACEHOLDER
    assert moderated[1]["moderation_status"] == "filtered"
