"""日志最终渲染脱敏与文件权限测试。"""

import logging
import stat
from collections import namedtuple

from src import log_config


def test_loguru_record_patcher_scrubs_message_and_exception_value():
    record_exception = namedtuple("RecordException", "type value traceback")
    record = {
        "message": "request token=topsecretvalue",
        "exception": record_exception(
            ValueError,
            ValueError("Bearer abcdefghijklmnop"),
            None,
        ),
    }

    log_config._scrub_loguru_record(record)

    assert "topsecretvalue" not in record["message"]
    assert "abcdefghijklmnop" not in str(record["exception"].value)
    assert "REDACTED" in record["message"]
    assert "REDACTED" in str(record["exception"].value)


def test_setup_logging_creates_private_directory_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(log_config, "_SETUP_DONE", False)

    log_config.setup_logging(json_log_dir=str(tmp_path / "logs"), console=False)
    logging.getLogger("security-test").error("token=topsecretvalue")
    try:
        raise ValueError("Bearer abcdefghijklmnop")
    except ValueError:
        logging.getLogger("security-test").exception("API failure token=anothersecretvalue")

    log_dir = tmp_path / "logs"
    files = list(log_dir.glob("*.log"))
    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert files
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "topsecretvalue" not in rendered
    assert "anothersecretvalue" not in rendered
    assert "abcdefghijklmnop" not in rendered

    log_config._loguru_logger.remove()
    monkeypatch.setattr(log_config, "_SETUP_DONE", False)
