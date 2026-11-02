"""Android 平台适配：运行时权限、UDP 多播锁、SAF 文件选择。

仅在 Android 上被调用；所有 ``jnius`` / ``android.*`` 导入都延迟到函数内部，
保证桌面环境 import 本模块不触发缺失依赖。
"""
from __future__ import annotations

import os

_REQUEST_FILE = 0x4A49
_REQUEST_TREE = 0x4A50
_PENDING: dict[int, tuple[str, object]] = {}
_multicast_lock = None


def request_permissions(callback=None) -> None:
    """申请运行时权限（旧版 Android 写外部存储需要）；回调布尔结果。"""
    from android.permissions import Permission, request_permissions as _req

    def done(permissions, grants):
        if callback:
            callback(all(grants))

    _req([Permission.WRITE_EXTERNAL_STORAGE], done)


def acquire_multicast_lock() -> None:
    """持有 MulticastLock，否则部分 ROM 会丢弃 UDP 广播/多播。"""
    global _multicast_lock
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    wifi = activity.getSystemService("wifi")
    _multicast_lock = wifi.createMulticastLock("jam_intranexus")
    _multicast_lock.acquire()


def release_multicast_lock() -> None:
    global _multicast_lock
    if _multicast_lock is not None:
        _multicast_lock.release()
        _multicast_lock = None


def _copy_stream_to_cache(uri, default_name: str) -> str:
    """把 content:// URI 复制到缓存目录，返回真实文件路径（用于发送）。"""
    from android import activity

    resolver = activity.mActivity.getContentResolver()
    stream = resolver.openInputStream(uri)
    name = str(uri.getLastPathSegment()) or default_name
    out = os.path.join(str(activity.mActivity.getCacheDir().getAbsolutePath()), name)
    buf = bytearray(64 * 1024)
    with open(out, "wb") as f:
        while True:
            n = stream.read(buf, 0, len(buf))
            if n <= 0:
                break
            f.write(bytes(buf[:n]))
    return out


def pick_file(callback) -> None:
    """SAF 打开文档（任意文件），选中后回调缓存文件路径。"""
    from android import activity
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    _PENDING[_REQUEST_FILE] = ("file", callback)
    intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType("*/*")
    activity.bind(on_activity_result=_on_activity_result)
    activity.startActivityForResult(intent, _REQUEST_FILE)


def pick_directory(callback) -> None:
    """SAF 打开目录树；回调文档 URI 字符串（SAF 下直接写文件受限，尽力而为）。"""
    from android import activity
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    _PENDING[_REQUEST_TREE] = ("tree", callback)
    intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
    activity.bind(on_activity_result=_on_activity_result)
    activity.startActivityForResult(intent, _REQUEST_TREE)


def _on_activity_result(request_code, result_code, intent):
    entry = _PENDING.pop(request_code, None)
    if entry is None:
        return
    kind, callback = entry
    if result_code != -1 or intent is None:  # RESULT_OK == -1
        return
    if kind == "file":
        callback(_copy_stream_to_cache(intent.getData(), "picked"))
    else:
        callback(str(intent.getData().toString()))
