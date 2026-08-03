"""FileTool 敏感文件边界测试。"""

from src.tools.file_tool import FileTool


def test_sensitive_files_are_denied(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    (config_dir / ".env").write_text("SECRET=value")
    (data_dir / "state.db").write_bytes(b"sqlite")
    (tmp_path / "private.pem").write_text("PRIVATE KEY")
    tool = FileTool(base_dir=str(tmp_path))

    for path in ("config/.env", "data/state.db", "private.pem"):
        result = tool.read(path)
        assert result["success"] is False
        assert "敏感" in result["error"]


def test_symlink_to_sensitive_file_is_denied(tmp_path):
    secret = tmp_path / ".env"
    secret.write_text("SECRET=value")
    (tmp_path / "safe-name.txt").symlink_to(secret)
    tool = FileTool(base_dir=str(tmp_path))

    result = tool.read("safe-name.txt")

    assert result["success"] is False
    assert "敏感" in result["error"]


def test_normal_project_file_remains_readable(tmp_path):
    (tmp_path / "safe.txt").write_text("hello")
    tool = FileTool(base_dir=str(tmp_path))

    result = tool.read("safe.txt")

    assert result["success"] is True
    assert "hello" in result["content"]


def test_list_and_search_hide_sensitive_files(tmp_path):
    (tmp_path / ".env").write_text("SECRET=value")
    (tmp_path / "state.db").write_bytes(b"sqlite")
    (tmp_path / "safe.txt").write_text("hello")
    tool = FileTool(base_dir=str(tmp_path))

    listed = tool.list_dir(".")
    searched = tool.search(".", "*")

    assert listed["success"] is True
    assert {item["name"] for item in listed["files"]} == {"safe.txt"}
    assert searched["success"] is True
    assert {item["name"] for item in searched["matches"]} == {"safe.txt"}
