"""日志兜底：轮转文件创建与写入。"""
import logging
import os

from core.logging_setup import LOG_FILENAME, setup_logging


def test_setup_writes_log_file(tmp_path):
    path = setup_logging(str(tmp_path))
    assert path == str(tmp_path / LOG_FILENAME)

    logging.getLogger("t").info("hello-log")
    for h in logging.getLogger().handlers:
        h.flush()

    assert os.path.exists(path)
    assert "hello-log" in open(path, encoding="utf-8").read()
