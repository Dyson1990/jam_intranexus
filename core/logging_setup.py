"""应用日志：轮转写入数据目录文件 + 捕获未处理异常。

真机脱离电脑时拿不到 logcat，故把日志与异常回溯落到应用私有目录文件，
便于事后取回；桌面端则双写（文件 + stderr/logcat）。
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_FILENAME = "app.log"
_configured = False


def setup_logging(log_dir: str) -> str:
    """配置根日志器写入轮转文件；幂等，返回日志文件路径。"""
    global _configured
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, LOG_FILENAME)
    if not _configured:
        handler = RotatingFileHandler(path, maxBytes=256 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        _configured = True

        def excepthook(exc_type, exc, tb):
            root.error("unhandled exception", exc_info=(exc_type, exc, tb))
            sys.__excepthook__(exc_type, exc, tb)

        sys.excepthook = excepthook
    return path


def install_asyncio_handler(loop) -> None:
    """把 asyncio 任务内未捕获异常也落盘（默认只打印警告，不写日志文件）。"""
    log = logging.getLogger("asyncio")

    def handler(_loop, context):
        exc = context.get("exception")
        if exc is not None:
            log.error(context.get("message", "task exception"),
                      exc_info=(type(exc), exc, exc.__traceback__))
        else:
            log.error(context.get("message", "asyncio error"))

    loop.set_exception_handler(handler)
