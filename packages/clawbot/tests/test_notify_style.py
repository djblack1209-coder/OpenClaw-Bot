from src.notify_style import format_announcement, format_digest, format_notice, format_trade_submitted, kv


def test_format_notice_keeps_uniform_layout():
    text = format_notice(
        "OpenClaw 提现提醒",
        bullets=[kv("单子", "Expensify/App#84449"), kv("动作", "去 Upwork 查看付款")],
        links=["https://github.com/Expensify/App/issues/84449"],
    )

    assert text.splitlines()[0] == "OpenClaw 提现提醒"
    assert " · 单子  Expensify/App#84449" in text
    assert " 🔗 https://github.com/Expensify/App/issues/84449" in text


def test_format_trade_submitted_uses_consistent_bullets():
    text = format_trade_submitted("buy", "nvda", 3, 12345, status="Submitted")

    assert text.startswith("🟢 挂单")
    assert "BUY NVDA x3" in text
    assert " · 订单号  #12345" in text


def test_format_digest_uses_announcement_style_sections():
    text = format_digest(
        "OpenClaw「科技早报」2026年03月08日",
        intro="今日聚焦 AI 与自动化两条主线。",
        sections=[
            ("【AI】", ["1. OpenAI 发布新模型", "   详情：https://example.com/ai"]),
            ("【Automation】", ["- 暂无新增"]),
        ],
        footer="更多详情请查看原文链接。",
    )

    assert text.splitlines()[0] == "📢  OpenClaw「科技早报」2026年03月08日"
    assert "今日聚焦 AI 与自动化两条主线。" in text
    assert "【AI】" in text
    assert "详情：https://example.com/ai" in text
    assert text.rstrip().endswith("更多详情请查看原文链接。")


def test_format_announcement_supports_links_block():
    text = format_announcement(
        "OpenClaw「资讯快讯」NVIDIA",
        intro="本轮命中 1 条新增资讯。",
        sections=[("【第 1 条】", ["1. NVIDIA 发布新 AI 平台（来源：Reuters）"])],
        links=["https://example.com/nvidia"],
        footer="如需继续追踪，可稍后再次扫描。",
    )

    assert text.startswith("📢  OpenClaw「资讯快讯」NVIDIA")
    assert "🔗 直达" in text
    assert text.rstrip().endswith("如需继续追踪，可稍后再次扫描。")
