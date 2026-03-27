"""sau_bridge 单元测试 — 社媒发布桥接层"""
import pytest
from unittest.mock import patch, AsyncMock

from src.sau_bridge import (
    PLATFORMS,
    get_supported_platforms,
    format_publish_result,
    publish_video,
    publish_note,
    publish_multi_platform,
    check_sau_installed,
)


class TestPlatforms:
    def test_platforms_has_four(self):
        assert len(PLATFORMS) == 4
        assert "douyin" in PLATFORMS
        assert "bilibili" in PLATFORMS
        assert "xiaohongshu" in PLATFORMS
        assert "kuaishou" in PLATFORMS

    def test_get_supported_platforms(self):
        p = get_supported_platforms()
        assert isinstance(p, dict)
        assert all("name" in v for v in p.values())


class TestFormatResult:
    def test_format_success(self):
        results = {"douyin": {"success": True}, "bilibili": {"success": False, "error": "未登录"}}
        msg = format_publish_result(results)
        assert "✅" in msg
        assert "❌" in msg
        assert "抖音" in msg

    def test_format_empty(self):
        msg = format_publish_result({})
        assert "发布结果" in msg


class TestPublishVideo:
    @pytest.mark.asyncio
    async def test_unsupported_platform(self):
        result = await publish_video("weibo", "/tmp/test.mp4", "test")
        assert not result["success"]
        assert "不支持" in result["error"]

    @pytest.mark.asyncio
    async def test_file_not_exist(self):
        result = await publish_video("douyin", "/nonexistent/video.mp4", "test")
        assert not result["success"]
        assert "不存在" in result["error"]


class TestPublishNote:
    @pytest.mark.asyncio
    async def test_unsupported_platform(self):
        result = await publish_note("weibo", ["/tmp/1.png"], "test")
        assert not result["success"]

    @pytest.mark.asyncio
    async def test_no_valid_images(self):
        result = await publish_note("xiaohongshu", ["/nonexistent/1.png"], "test")
        assert not result["success"]
        assert "有效" in result["error"]

    @pytest.mark.asyncio
    async def test_bilibili_no_note_support(self):
        result = await publish_note("bilibili", ["/tmp/1.png"], "test")
        assert not result["success"]
        assert "不支持" in result["error"]
