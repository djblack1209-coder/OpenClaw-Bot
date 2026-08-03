from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.execution.social.x_auto_ops import (
    TrendSeed,
    VideoSeed,
    build_daily_drafts,
    build_next_draft,
    build_xhs_review_drafts,
    choose_seed,
    choose_seeds,
    compose_x_post,
    compose_xhs_note,
    distill_seed,
    extract_youtube_caption_urls,
    fetch_all_content_seeds,
    fetch_google_news_trending_seeds,
    get_next_reviewable_drafts,
    get_or_build_next_ready_draft,
    is_draft_approved,
    mark_draft_review,
    next_morning_at,
    parse_daily_times,
    require_draft_review,
    score_content_seed,
    summarize_transcript,
    write_launchd_plist,
    x_weighted_length,
)


def test_choose_seed_prefers_relevant_unseen_video():
    state = {"seen": []}
    seeds = [
        VideoSeed(title="football transfer drama", channel="sports", url="https://example.com/1"),
        VideoSeed(title="Claude agents changed my coding workflow", channel="AI Explained", url="https://example.com/2"),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("Claude agents")


def test_choose_seed_prefers_hot_trend_over_ai_vertical_video():
    state = {"seen": []}
    seeds = [
        VideoSeed(title="Claude agents changed my coding workflow", channel="AI Explained", url="https://example.com/ai"),
        TrendSeed(
            title="年轻人开始把工位布置成赛博寺庙",
            channel="微博热搜",
            url="https://s.weibo.com/weibo?q=%23demo%23",
            source="weibo",
            language="zh",
            raw_score=960000,
            raw_rank=2,
            heat_reason="高热中文话题，自带反差和抽象讨论空间",
            tags=["热点", "抽象"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("年轻人开始")


def test_score_content_seed_penalizes_tragedy_for_funny_auto_ops():
    playful = TrendSeed(
        title="全网开始挑战用一句话证明自己真的很累",
        channel="Google News",
        url="https://example.com/playful",
        source="google_news_us",
        language="en",
        raw_score=500,
        raw_rank=3,
    )
    tragedy = TrendSeed(
        title="Breaking: shooting leaves multiple people killed",
        channel="Google News",
        url="https://example.com/tragedy",
        source="google_news_us",
        language="en",
        raw_score=500,
        raw_rank=1,
    )

    assert score_content_seed(playful) > score_content_seed(tragedy)


def test_choose_seed_skips_official_politics_for_playful_trend():
    state = {"seen": []}
    seeds = [
        TrendSeed(
            title="总书记引领强国之路丨体育强则中国强",
            channel="Google News 中文",
            url="https://example.com/official",
            source="google_news_cn",
            language="zh",
            raw_score=999999,
            raw_rank=1,
        ),
        TrendSeed(
            title="年轻人开始把下班路当成每日副本",
            channel="微博热搜",
            url="https://example.com/playful",
            source="weibo",
            language="zh",
            raw_score=100,
            raw_rank=8,
            tags=["热点", "抽象"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("年轻人")


def test_choose_seed_skips_official_news_center_headline():
    state = {"seen": []}
    seeds = [
        TrendSeed(
            title="【牢记初心使命 奋进复兴征程】为民，初心永不变 - 中国网新闻中心",
            channel="Google News 中文",
            url="https://example.com/official-news",
            source="google_news_cn",
            language="zh",
            raw_score=999999,
            raw_rank=1,
        ),
        TrendSeed(
            title="网友把周一早会称为灵魂出厂设置",
            channel="微博热搜",
            url="https://example.com/fun",
            source="weibo",
            language="zh",
            raw_score=100,
            raw_rank=9,
            tags=["抽象"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("网友")


def test_choose_seed_skips_ai_vertical_when_user_wants_broader_hotspots():
    state = {"seen": []}
    seeds = [
        TrendSeed(
            title="GLM-5.2 – How to Run Locally",
            channel="Hacker News",
            url="https://example.com/glm",
            source="hacker_news",
            language="en",
            raw_score=999999,
            raw_rank=1,
        ),
        TrendSeed(
            title="Steam Machine launches today",
            channel="Hacker News",
            url="https://example.com/steam",
            source="hacker_news",
            language="en",
            raw_score=100,
            raw_rank=3,
            tags=["Internet", "Tech"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("Steam")


def test_score_content_seed_penalizes_generic_sports_fixture():
    playful = TrendSeed(
        title="网友把通勤路线画成魂系地图",
        channel="微博热搜",
        url="https://example.com/meme",
        source="weibo",
        language="zh",
        raw_score=1000,
        raw_rank=6,
        tags=["抽象"],
    )
    fixture = TrendSeed(
        title="世界杯：法国vs伊拉克",
        channel="百度热搜",
        url="https://example.com/match",
        source="baidu",
        language="zh",
        raw_score=900000,
        raw_rank=1,
    )

    assert score_content_seed(playful) > score_content_seed(fixture)


def test_choose_seed_skips_generic_sports_star_news():
    state = {"seen": []}
    seeds = [
        TrendSeed(
            title="姆巴佩世界波破门",
            channel="头条热榜",
            url="https://example.com/sports",
            source="toutiao",
            language="zh",
            raw_score=999999,
            raw_rank=1,
        ),
        TrendSeed(
            title="玩家把游戏BUG做成年度行为艺术",
            channel="B站热榜",
            url="https://example.com/game",
            source="bilibili_trending",
            language="zh",
            raw_score=100,
            raw_rank=8,
            tags=["游戏", "抽象"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("玩家")


def test_choose_seed_skips_hard_news_for_funny_account():
    state = {"seen": []}
    seeds = [
        TrendSeed(
            title="近4000家外资企业追加在华投资",
            channel="头条热榜",
            url="https://example.com/business",
            source="toutiao",
            language="zh",
            raw_score=999999,
            raw_rank=1,
        ),
        TrendSeed(
            title="网友把周一早会称为灵魂出厂设置",
            channel="微博热搜",
            url="https://example.com/fun",
            source="weibo",
            language="zh",
            raw_score=100,
            raw_rank=9,
            tags=["抽象"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("网友")


def test_choose_seed_skips_exam_weather_and_serious_news_for_fun_account():
    state = {"seen": []}
    seeds = [
        TrendSeed(
            title="高考查分",
            channel="百度热榜",
            url="https://example.com/exam",
            source="baidu",
            language="zh",
            raw_score=999999,
            raw_rank=1,
        ),
        TrendSeed(
            title="未来这些地方雨水还将超长待机",
            channel="百度热榜",
            url="https://example.com/weather",
            source="baidu",
            language="zh",
            raw_score=888888,
            raw_rank=2,
        ),
        TrendSeed(
            title="UP主一己之力下架导航广告",
            channel="B站热榜",
            url="https://example.com/up",
            source="bilibili_trending",
            language="zh",
            raw_score=100,
            raw_rank=8,
            tags=["Bilibili", "网友"],
        ),
    ]

    chosen = choose_seed(seeds, state)

    assert chosen.title.startswith("UP主")


def test_choose_seeds_requires_fun_signal_for_generic_news_sources():
    seeds = [
        TrendSeed(
            title="全球资产全线下跌",
            channel="百度热榜",
            url="https://example.com/market",
            source="baidu",
            language="zh",
            raw_score=900000,
            raw_rank=1,
        ),
        TrendSeed(
            title="多名艺人痛失艺名",
            channel="百度热榜",
            url="https://example.com/stage-name",
            source="baidu",
            language="zh",
            raw_score=800000,
            raw_rank=2,
            tags=["热点"],
        ),
        TrendSeed(
            title="Show HN: Got sick of ads, so I made my own logic puzzle site",
            channel="Hacker News",
            url="https://example.com/puzzle",
            source="hacker_news",
            language="en",
            raw_score=500,
            raw_rank=4,
            tags=["Internet"],
        ),
    ]

    chosen = choose_seeds(seeds, {"seen": []}, count=2)
    titles = " ".join(seed.title for seed in chosen)

    assert "全球资产" not in titles
    assert "艺名" in titles
    assert "logic puzzle" in titles


def test_compose_x_post_for_hot_trend_uses_abstract_fun_style_without_ai_branding():
    seed = TrendSeed(
        title="年轻人开始把工位布置成赛博寺庙",
        channel="微博热搜",
        url="https://s.weibo.com/weibo?q=%23demo%23",
        source="weibo",
        language="zh",
        raw_score=960000,
        raw_rank=2,
        heat_reason="工作压力和玄学安慰发生了奇妙合流",
        tags=["热点", "抽象"],
    )

    post = compose_x_post(seed, angle="internet_mood")

    assert "赛博寺庙" in post
    assert "精神病历" in post
    assert "#OpenClaw" not in post
    assert x_weighted_length(post) <= 250


def test_compose_xhs_note_uses_reviewable_lifestyle_style():
    seed = TrendSeed(
        title="多名艺人痛失艺名",
        channel="百度热榜",
        url="https://example.com/stage-name",
        source="baidu",
        language="zh",
        raw_score=900000,
        raw_rank=2,
        tags=["热点"],
        heat_reason="娱乐梗和名字权属发生了奇妙合流",
    )

    note = compose_xhs_note(seed, angle="abstract_roast")

    assert "艺名" in note["title"]
    assert "越看越抽象" in note["title"]
    assert len(note["body"]) <= 900
    assert "小红书" not in note["body"]


def test_build_xhs_review_drafts_creates_pending_notes(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="多名艺人痛失艺名",
                channel="百度热榜",
                url="https://example.com/stage-name",
                source="baidu",
                language="zh",
                raw_score=900000,
                raw_rank=2,
                tags=["热点"],
            ),
            TrendSeed(
                title="UP主一己之力下架导航广告",
                channel="B站热榜",
                url="https://example.com/up",
                source="bilibili_trending",
                language="zh",
                raw_score=100,
                raw_rank=8,
                tags=["Bilibili"],
            ),
        ],
    )
    state_path = tmp_path / "x_auto_ops_state.json"

    drafts = build_xhs_review_drafts(count=2, state_path=state_path)

    assert len(drafts) == 2
    assert all(draft["platform"] == "xhs" for draft in drafts)
    assert all(draft["status"] == "needs_review" for draft in drafts)
    assert all(draft["review_status"] == "pending" for draft in drafts)
    assert all(draft.get("title") and draft.get("body") for draft in drafts)


def test_build_daily_drafts_supersedes_old_ai_ready_drafts(monkeypatch, tmp_path):
    state_path = tmp_path / "x_auto_ops_state.json"
    state_path.write_text(
        """{
          "seen": [],
          "drafts": [
            {
              "id": "old-ai",
              "platform": "x",
              "status": "ready",
              "angle": "founder_note",
              "text": "OpenClaw 自动蒸馏：AI Explained｜Claude demo",
              "seed": {"source": "youtube_rss", "title": "Claude demo"}
            }
          ],
          "scheduled": [],
          "published": [],
          "daily_times": ["08:30"]
        }""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="全网开始挑战用一句话证明自己真的很累",
                channel="Google News",
                url="https://example.com/tired",
                source="google_news_us",
                language="en",
                raw_score=800,
                raw_rank=1,
                tags=["Trending", "Internet"],
            )
        ],
    )

    drafts = build_daily_drafts(count=2, state_path=state_path, fetch_transcript=False)

    assert len(drafts) == 2
    loaded = state_path.read_text(encoding="utf-8")
    assert '"status": "superseded"' in loaded
    assert all("自动蒸馏" not in draft["text"] for draft in drafts)


def test_build_daily_drafts_balances_chinese_and_english_trends(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            *[
                TrendSeed(
                    title=f"英文科技热点 {idx}",
                    channel="Hacker News",
                    url=f"https://example.com/en-{idx}",
                    source="hacker_news",
                    language="en",
                    raw_score=999999 - idx,
                    raw_rank=idx + 1,
                    tags=["Internet"],
                )
                for idx in range(8)
            ],
            *[
                TrendSeed(
                    title=f"中文抽象热点 {idx}",
                    channel="微博热搜",
                    url=f"https://example.com/zh-{idx}",
                    source="bilibili_trending",
                    language="zh",
                    raw_score=10 - idx,
                    raw_rank=10 + idx,
                    tags=["热点", "抽象"],
                )
                for idx in range(3)
            ],
        ],
    )
    state_path = tmp_path / "x_auto_ops_state.json"

    drafts = build_daily_drafts(count=6, state_path=state_path, fetch_transcript=False)

    languages = [draft["seed"].get("language") for draft in drafts]
    assert languages.count("zh") >= 2
    assert languages.count("en") >= 2


def test_build_daily_drafts_filters_official_and_ai_vertical_items(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="信仰强基 理论固本 思想铸魂",
                channel="百度热榜",
                url="https://example.com/official",
                source="baidu",
                language="zh",
                raw_score=999999,
                raw_rank=1,
            ),
            TrendSeed(
                title="GLM-5.2 – How to Run Locally",
                channel="Hacker News",
                url="https://example.com/glm",
                source="hacker_news",
                language="en",
                raw_score=999999,
                raw_rank=2,
            ),
            TrendSeed(
                title="微信迎来史上最大更新",
                channel="百度热榜",
                url="https://example.com/wechat",
                source="baidu",
                language="zh",
                raw_score=800000,
                raw_rank=3,
                tags=["热点"],
            ),
            TrendSeed(
                title="Steam Machine launches today",
                channel="Hacker News",
                url="https://example.com/steam",
                source="hacker_news",
                language="en",
                raw_score=600000,
                raw_rank=4,
                tags=["Internet", "Tech"],
            ),
        ],
    )
    state_path = tmp_path / "x_auto_ops_state.json"

    drafts = build_daily_drafts(count=4, state_path=state_path, fetch_transcript=False)
    titles = " ".join(draft["seed"]["title"] for draft in drafts)

    assert "信仰强基" not in titles
    assert "GLM-5.2" not in titles
    assert "微信迎来史上最大更新" in titles or "Steam Machine" in titles


def test_build_daily_drafts_replaces_stale_ready_hot_drafts(monkeypatch, tmp_path):
    state_path = tmp_path / "x_auto_ops_state.json"
    state_path.write_text(
        """{
          "seen": [],
          "drafts": [
            {
              "id": "old-hot",
              "platform": "x",
              "status": "ready",
              "angle": "internet_mood",
              "text": "今日互联网精神状态：旧热点",
              "seed": {"source": "hacker_news", "title": "旧热点", "language": "en"}
            }
          ],
          "scheduled": [],
          "published": [],
          "daily_times": ["08:30"]
        }""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title=f"新热点 {idx}",
                channel="微博热搜",
                url=f"https://example.com/new-{idx}",
                source="weibo",
                language="zh",
                raw_score=900000 - idx,
                raw_rank=idx + 1,
            )
            for idx in range(6)
        ],
    )

    drafts = build_daily_drafts(count=3, state_path=state_path, fetch_transcript=False)
    loaded = state_path.read_text(encoding="utf-8")

    assert len(drafts) == 3
    assert '"id": "old-hot"' in loaded
    assert '"status": "superseded"' in loaded
    assert all(draft["id"] != "old-hot" for draft in drafts)


def test_build_daily_drafts_reactivates_same_superseded_draft_ids(monkeypatch, tmp_path):
    seed = TrendSeed(
        title="重复热点但仍未发布",
        channel="Hacker News",
        url="https://example.com/reuse",
        source="hacker_news",
        language="en",
        raw_score=3000,
        raw_rank=1,
        tags=["Internet"],
    )
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_all_content_seeds", lambda: [seed])
    state_path = tmp_path / "x_auto_ops_state.json"

    first = build_daily_drafts(count=1, state_path=state_path, fetch_transcript=False)
    second = build_daily_drafts(count=1, state_path=state_path, fetch_transcript=False)
    loaded = __import__("json").loads(state_path.read_text(encoding="utf-8"))
    ready = [draft for draft in loaded["drafts"] if draft.get("status") == "ready"]

    assert first[0]["id"] == second[0]["id"]
    assert len(ready) == 1
    assert ready[0]["id"] == second[0]["id"]


def test_build_daily_drafts_does_not_repeat_same_topic_with_different_angles(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="降价也卖不动 合资燃油车撤出门店",
                channel="百度热搜",
                url="https://example.com/car",
                source="baidu",
                language="zh",
                raw_score=900000,
                raw_rank=1,
            ),
            TrendSeed(
                title="降价也卖不动，合资燃油车撤出门店",
                channel="头条热榜",
                url="https://example.com/car-2",
                source="toutiao",
                language="zh",
                raw_score=800000,
                raw_rank=2,
            ),
            TrendSeed(
                title="Deno Desktop",
                channel="Hacker News",
                url="https://example.com/deno",
                source="hacker_news",
                language="en",
                raw_score=8000,
                raw_rank=1,
            ),
        ],
    )
    state_path = tmp_path / "x_auto_ops_state.json"

    drafts = build_daily_drafts(count=4, state_path=state_path, fetch_transcript=False)
    titles = [draft["seed"]["title"] for draft in drafts]

    assert len(titles) == len(set(titles))


def test_choose_seeds_deduplicates_same_topic_across_sources():
    from src.execution.social.x_auto_ops import choose_seeds

    seeds = [
        TrendSeed(
            title="网友锐评降价也卖不动合资燃油车撤出门店",
            channel="百度热搜",
            url="https://example.com/car-a",
            source="baidu",
            language="zh",
            raw_score=900000,
            raw_rank=1,
        ),
        TrendSeed(
            title="网友锐评：降价也卖不动，合资燃油车撤出门店",
            channel="头条热榜",
            url="https://example.com/car-b",
            source="toutiao",
            language="zh",
            raw_score=850000,
            raw_rank=2,
        ),
        TrendSeed(
            title="Deno Desktop",
            channel="Hacker News",
            url="https://example.com/deno",
            source="hacker_news",
            language="en",
            raw_score=6000,
            raw_rank=1,
        ),
    ]

    chosen = choose_seeds(seeds, {"seen": []}, count=3)
    normalized_titles = [
        title.replace("：", "").replace("，", "").replace(" ", "")
        for title in [seed.title for seed in chosen]
    ]

    assert normalized_titles.count("网友锐评降价也卖不动合资燃油车撤出门店") == 1


def test_fetch_google_news_trending_seeds_ignores_incomplete_read(monkeypatch):
    import http.client

    def boom(url, timeout=10):
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr("src.execution.social.x_auto_ops._http_get_text", boom)

    assert fetch_google_news_trending_seeds() == []


def test_fetch_all_content_seeds_uses_free_api_chinese_fallback(monkeypatch):
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_real_trending_seeds", lambda: [])
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_google_news_trending_seeds", lambda: [])
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_hacker_news_trending_seeds", lambda: [])
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_bilibili_trending_seeds", lambda limit=10: [])
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_youtube_rss_seeds", lambda per_channel=1: [])
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_free_api_trending_seeds",
        lambda: [
            TrendSeed(
                title="年轻人开始挑战下班后不说人话",
                channel="头条热榜",
                url="https://example.com/toutiao",
                source="toutiao",
                language="zh",
                raw_score=123456,
                raw_rank=1,
                tags=["热点"],
            )
        ],
    )

    seeds = fetch_all_content_seeds(include_video_fallback=False)

    assert seeds
    assert seeds[0].source == "toutiao"
    assert seeds[0].language == "zh"


def test_extract_youtube_caption_urls_supports_escaped_base_url():
    page = '{"captionTracks":[{"baseUrl":"https:\\/\\/www.youtube.com\\/api\\/timedtext?v=abc\\u0026lang=en"}]}'

    urls = extract_youtube_caption_urls(page)

    assert urls == ["https://www.youtube.com/api/timedtext?v=abc&lang=en"]


def test_summarize_transcript_extracts_keyword_sentences():
    transcript = (
        "This video explains why AI agents change developer workflow. "
        "The important part is building an automation loop that can run every day. "
        "A random unrelated sentence follows."
    )

    summary = summarize_transcript(transcript)

    assert "agents" in summary.lower() or "automation" in summary.lower()
    assert len(summary) < 600


def test_distill_seed_adds_summary_and_tags_without_network(monkeypatch):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_youtube_transcript",
        lambda url: "AI agents can automate the coding workflow and content workflow.",
    )
    seed = VideoSeed(title="AI agents for coding", channel="Demo", url="https://www.youtube.com/watch?v=abc123")

    distilled = distill_seed(seed)

    assert distilled.transcript
    assert distilled.summary
    assert "AI" in distilled.tags


def test_compose_x_post_contains_operating_loop_and_source():
    seed = VideoSeed(
        title="Claude agents changed my coding workflow",
        channel="AI Explained",
        url="https://youtu.be/demo",
        summary="AI agents changed coding workflow into a repeatable automation loop.",
        tags=["AI", "Agent"],
    )

    post = compose_x_post(seed)

    assert "OpenClaw" in post
    assert "AI Explained" in post
    assert "https://youtu.be/demo" in post
    assert "agent" in post.lower()
    assert len(post) < 3800


def test_compose_x_post_supports_multiple_angles():
    seed = VideoSeed(title="AI agents for real workflows", channel="Fireship", url="https://youtu.be/1")

    post = compose_x_post(seed, angle="contrarian")

    assert "反常识" in post
    assert "#OpenClaw" in post


def test_build_next_draft_persists_state(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="全网开始挑战用一句话证明自己真的很累",
                channel="微博热搜",
                url="https://example.com/tired",
                source="weibo",
                language="zh",
                raw_score=900000,
                raw_rank=1,
            )
        ],
    )
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_youtube_transcript", lambda url: "AI agents automate workflows.")
    state_path = tmp_path / "x_auto_ops_state.json"

    draft = build_next_draft(state_path)

    assert draft["status"] == "ready"
    assert draft["platform"] == "x"
    assert "一句话证明自己真的很累" in draft["seed"]["title"]
    assert state_path.exists()


def test_x_auto_drafts_require_human_review_before_publish(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="网友把周一早会称为灵魂出厂设置",
                channel="微博热搜",
                url="https://example.com/monday",
                source="weibo",
                language="zh",
                raw_score=900000,
                raw_rank=1,
            )
        ],
    )
    state_path = tmp_path / "x_auto_ops_state.json"

    draft = build_next_draft(state_path=state_path, fetch_transcript=False)
    blocked = require_draft_review(draft, state_path=state_path)
    pending = get_next_reviewable_drafts(state_path=state_path)

    assert draft["review_status"] == "pending"
    assert blocked["requires_review"] is True
    assert pending[0]["status"] == "needs_review"
    assert not is_draft_approved(pending[0])


def test_x_auto_approved_draft_can_be_selected_for_publish(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title="大家开始用一句话形容自己的精神状态",
                channel="百度热搜",
                url="https://example.com/mood",
                source="baidu",
                language="zh",
                raw_score=800000,
                raw_rank=2,
            )
        ],
    )
    state_path = tmp_path / "x_auto_ops_state.json"
    draft = build_next_draft(state_path=state_path, fetch_transcript=False)

    approval = mark_draft_review(draft["id"], approved=True, reviewer="owner", state_path=state_path)
    selected = get_or_build_next_ready_draft(state_path=state_path)

    assert approval["success"] is True
    assert approval["draft"]["review_status"] == "approved"
    assert selected["id"] == draft["id"]
    assert is_draft_approved(selected)


def test_build_daily_drafts_creates_5_to_8_ready_posts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            TrendSeed(
                title=f"今日互联网抽象热点 {idx}",
                channel="微博热搜",
                url=f"https://example.com/{idx}",
                source="weibo",
                language="zh",
                raw_score=800000 - idx,
                raw_rank=idx + 1,
            )
            for idx in range(8)
        ],
    )
    monkeypatch.setattr("src.execution.social.x_auto_ops.fetch_youtube_transcript", lambda url: "AI agents automate workflows.")
    state_path = tmp_path / "x_auto_ops_state.json"

    drafts = build_daily_drafts(count=6, state_path=state_path)

    assert len(drafts) == 6
    assert all(draft["status"] == "ready" for draft in drafts)
    assert len({draft["id"] for draft in drafts}) == 6


def test_parse_daily_times_ignores_invalid_values():
    times = parse_daily_times("08:30,bad,20:05,26:00")

    assert times == [(8, 30), (20, 5)]


def test_write_launchd_plist_defaults_to_daily_calendar_time(tmp_path):
    target = datetime(2026, 6, 23, 8, 30, tzinfo=ZoneInfo("America/Denver"))
    plist = write_launchd_plist(
        script_path=Path("/tmp/x_auto_morning_post.py"),
        target_time=target,
        plist_path=tmp_path / "com.openclaw.x-auto-morning-post.plist",
        daily_times=[(8, 30)],
    )
    text = plist.read_text(encoding="utf-8")

    assert "com.openclaw.x-auto-morning-post" in text
    assert "<key>Day</key>" not in text
    assert "<key>Hour</key><integer>8</integer>" in text
    assert "<key>Minute</key><integer>30</integer>" in text
    assert "--publish-next" not in text
    assert "--draft" in text
    assert "--draft-count" in text


def test_write_launchd_plist_supports_multiple_daily_times(tmp_path):
    target = datetime(2026, 6, 23, 8, 30, tzinfo=ZoneInfo("America/Denver"))
    plist = write_launchd_plist(
        script_path=Path("/tmp/x_auto_morning_post.py"),
        target_time=target,
        plist_path=tmp_path / "com.openclaw.x-auto-morning-post.plist",
        daily_times=[(8, 30), (10, 30), (20, 5)],
    )
    text = plist.read_text(encoding="utf-8")

    assert "<array>" in text
    assert text.count("<key>Hour</key>") == 3
    assert "<key>Minute</key><integer>5</integer>" in text


def test_write_launchd_plist_can_write_one_shot_calendar_time(tmp_path):
    target = datetime(2026, 6, 23, 8, 30, tzinfo=ZoneInfo("America/Denver"))
    plist = write_launchd_plist(
        script_path=Path("/tmp/x_auto_morning_post.py"),
        target_time=target,
        plist_path=tmp_path / "com.openclaw.x-auto-morning-post.plist",
        repeat_daily=False,
    )
    text = plist.read_text(encoding="utf-8")

    assert "<key>Day</key><integer>23</integer>" in text
    assert "<key>Hour</key><integer>8</integer>" in text


def test_next_morning_at_returns_future_time():
    target = next_morning_at(hour=8, minute=30)

    assert target.tzinfo is not None
    assert target.hour == 8
    assert target.minute == 30


def test_social_browser_worker_loads_twikit_cookie(monkeypatch, tmp_path):
    import importlib.util
    import json

    worker_path = Path(__file__).resolve().parents[1] / "scripts" / "social_browser_worker.py"
    cookie_path = tmp_path / "x_cookies.json"
    cookie_path.write_text(json.dumps({"auth_token": "token-demo", "ct0": "csrf-demo"}), encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_X_TWIKIT_COOKIE_FILE", str(cookie_path))
    spec = importlib.util.spec_from_file_location("social_browser_worker_cookie_test", worker_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    cookies = module.load_cookies("x.com")

    names = {cookie["name"] for cookie in cookies}
    assert {"auth_token", "ct0"} <= names
    assert module.cookie_status(cookies)[0] is True


def test_social_browser_worker_extracts_matching_status_url(monkeypatch, tmp_path):
    import importlib.util

    worker_path = Path(__file__).resolve().parents[1] / "scripts" / "social_browser_worker.py"
    cookie_path = tmp_path / "x_cookies.json"
    cookie_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_X_TWIKIT_COOKIE_FILE", str(cookie_path))
    spec = importlib.util.spec_from_file_location("social_browser_worker_status_test", worker_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    rows = [
        {"text": "旧内容", "links": ["https://x.com/BonoDJblack/status/111/analytics"]},
        {"text": "OpenClaw 自动蒸馏：Fireship｜The most trusted code", "links": ["https://x.com/BonoDJblack/status/222/analytics"]},
    ]

    assert module._extract_matching_x_status_url(rows, "OpenClaw 自动蒸馏：Fireship") == "https://x.com/BonoDJblack/status/222"
