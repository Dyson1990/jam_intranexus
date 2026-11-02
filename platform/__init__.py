"""平台适配：默认路径、权限、多播锁、文件选择。

桌面（Windows/Linux/macOS）多数能力为 no-op 或走 Kivy FileChooser；
Android 通过 PyJnius 申请运行时权限、持有 MulticastLock、用 SAF 选文件。
"""
from __future__ import annotations

import os
import socket


def is_android() -> bool:
    from kivy.utils import platform

    return platform == "android"


def default_name() -> str:
    try:
        name = socket.gethostname()
    except OSError:
        name = ""
    return name or "Device"


def default_save_dir() -> str:
    if is_android():
        return os.path.join(os.environ.get("EXTERNAL_STORAGE", "/sdcard"), "Download")
    return os.path.join(os.path.expanduser("~"), "Downloads")


def setup_hints() -> list[str]:
    """返回当前平台需要提示用户的一次性说明（如防火墙放行）。"""
    if is_android():
        return []
    return ["首次运行请在系统防火墙放行：TCP 47900（收发）与 UDP 47899（发现）"]


def request_permissions(callback=None) -> None:
    if is_android():
        from .android import request_permissions as _req

        _req(callback)
    elif callback:
        callback(True)


def acquire_multicast_lock() -> None:
    if is_android():
        from .android import acquire_multicast_lock

        acquire_multicast_lock()


def release_multicast_lock() -> None:
    if is_android():
        from .android import release_multicast_lock

        release_multicast_lock()


def pick_file(callback) -> None:
    """选择单个文件；选中后回调路径。"""
    if is_android():
        from .android import pick_file as _pf

        _pf(callback)
    else:
        from kivy.uix.filechooser import FileChooserListView

        _pick(FileChooserListView, "选择文件", True, callback)


def pick_directory(callback) -> None:
    """选择目录；选中后回调路径。"""
    if is_android():
        from .android import pick_directory as _pd

        _pd(callback)
    else:
        from kivy.uix.filechooser import FileChooserListView

        _pick(FileChooserListView, "选择目录", False, callback)


def _pick(chooser_cls, title: str, files: bool, callback) -> None:
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.popup import Popup

    chooser = chooser_cls(dirselect=not files, multiselect=False)
    content = BoxLayout(orientation="vertical", spacing="6dp", padding="6dp")
    content.add_widget(chooser)
    ok = Button(text="确定", size_hint_y=None, height="48dp")
    content.add_widget(ok)
    popup = Popup(title=title, content=content, size_hint=(0.9, 0.85))

    def choose(_):
        popup.dismiss()
        if files:
            if chooser.selection:
                callback(chooser.selection[0])
        else:
            callback(chooser.path)

    ok.bind(on_release=choose)
    popup.open()
