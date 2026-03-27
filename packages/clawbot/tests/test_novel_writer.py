"""novel_writer 单元测试 — AI 小说写作引擎"""
import pytest
import tempfile
from pathlib import Path

from src.novel_writer import NovelWriter


@pytest.fixture
def writer(tmp_path):
    """使用临时数据库的 NovelWriter"""
    db_path = tmp_path / "test_novels.db"
    return NovelWriter(db_path=str(db_path))


class TestNovelWriterInit:
    def test_init_creates_db(self, writer):
        assert writer.db_path.exists()

    def test_init_creates_tables(self, writer):
        with writer._conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t["name"] for t in tables]
            assert "novels" in table_names
            assert "chapters" in table_names


class TestListNovels:
    def test_empty_list(self, writer):
        novels = writer.list_novels()
        assert novels == []


class TestGetNovelStatus:
    def test_nonexistent_novel(self, writer):
        status = writer.get_novel_status(999)
        assert "error" in status


class TestExport:
    def test_export_nonexistent(self, writer):
        result = writer.export_txt(999)
        assert result is None

    def test_export_empty_novel(self, writer):
        # 手动插入一个没有章节的小说
        with writer._conn() as conn:
            conn.execute(
                "INSERT INTO novels (title, genre, style) VALUES (?, ?, ?)",
                ("测试小说", "测试", "测试风格")
            )
        result = writer.export_txt(1)
        assert result is None  # 无章节不导出

    def test_export_with_chapters(self, writer):
        with writer._conn() as conn:
            conn.execute(
                "INSERT INTO novels (title, genre, style) VALUES (?, ?, ?)",
                ("测试小说", "都市", "轻松")
            )
            conn.execute(
                "INSERT INTO chapters (novel_id, chapter_num, title, content, word_count) VALUES (?,?,?,?,?)",
                (1, 1, "序章", "这是第一章的内容。" * 100, 900)
            )
        result = writer.export_txt(1)
        assert result is not None
        assert Path(result).exists()
        content = Path(result).read_text(encoding="utf-8")
        assert "测试小说" in content
        assert "这是第一章的内容" in content
