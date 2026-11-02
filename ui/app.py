"""Kivy 应用：赛博朋克主题 + 四大页面导航 + 会话后端接线。"""
from __future__ import annotations

import asyncio
import os

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from .screens import ChatScreen, DeviceListScreen, SettingsScreen, TransferScreen
from .theme import BG, CYAN, DIM, MAGENTA, PANEL, TEXT, register_cjk_font

KV = """
#:import BG ui.theme.BG
#:import PANEL ui.theme.PANEL
#:import CYAN ui.theme.CYAN
#:import MAGENTA ui.theme.MAGENTA
#:import TEXT ui.theme.TEXT

<RootWidget>:
    orientation: 'vertical'
    canvas.before:
        Color:
            rgba: BG
        Rectangle:
            pos: self.pos
            size: self.size
    ScreenManager:
        id: sm
        DeviceListScreen:
            name: 'devicelistscreen'
        ChatScreen:
            name: 'chatscreen'
        TransferScreen:
            name: 'transferscreen'
        SettingsScreen:
            name: 'settingsscreen'
    BoxLayout:
        id: nav
        size_hint_y: None
        height: '60dp'
        spacing: '6dp'
        padding: '8dp'
        canvas.before:
            Color:
                rgba: PANEL
            Rectangle:
                pos: self.pos
                size: self.size
        NeonToggle:
            text: '设备'
            group: 'nav'
            state: 'down'
            on_release: sm.current = 'devicelistscreen'
        NeonToggle:
            text: '消息'
            group: 'nav'
            on_release: sm.current = 'chatscreen'
        NeonToggle:
            text: '传输'
            group: 'nav'
            on_release: sm.current = 'transferscreen'
        NeonToggle:
            text: '设置'
            group: 'nav'
            on_release: sm.current = 'settingsscreen'
"""


class RootWidget(BoxLayout):
    pass


class IntranexusApp(App):
    title = "jam_intranexus"

    def build(self):
        register_cjk_font()
        Builder.load_string(KV)
        self.current_peer_id = None
        self.current_peer_name = ""
        self.current_peer_address = ""
        return RootWidget()

    def on_start(self):
        from core.logging_setup import install_asyncio_handler, setup_logging
        from core.session import Session
        from plat import acquire_multicast_lock, request_permissions

        db_dir = self.user_data_dir or os.path.join(os.path.expanduser("~"), ".jam_intranexus")
        os.makedirs(db_dir, exist_ok=True)
        setup_logging(db_dir)
        install_asyncio_handler(asyncio.get_running_loop())
        acquire_multicast_lock()
        request_permissions()
        self.session = Session(os.path.join(db_dir, "data.db"))
        self.session.on_peers_changed = lambda: self._post(self._refresh_devices)
        self.session.on_message = lambda msg, peer: self._post(lambda: self._on_message(msg, peer))
        self.session.on_status = lambda msg, peer: self._post(lambda: self._on_message(msg, peer))
        self.session.on_transfer_changed = lambda: self._post(self._refresh_transfers)
        self.call_async(self.session.start())
        # 各页面初始刷新
        self._post(self._refresh_devices)
        self._post(self._refresh_transfers)
        self._post(lambda: self._screen("settingsscreen").refresh())

    def on_stop(self):
        from plat import release_multicast_lock

        if getattr(self, "session", None) is not None:
            try:
                self.session.db.close()
            except Exception:
                pass
        release_multicast_lock()

    # ---- 工具 ----
    def call_async(self, coro) -> None:
        asyncio.ensure_future(coro)

    def _post(self, fn) -> None:
        Clock.schedule_once(lambda dt: fn())

    def _screen(self, name):
        return self.root.ids.sm.get_screen(name)

    def toast(self, text: str) -> None:
        popup = Popup(title="提示", content=Label(text=text, color=TEXT, halign="center", valign="middle"),
                      size_hint=(0.7, 0.25))
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 2.0)

    # ---- 分发 ----
    def _refresh_devices(self):
        self._screen("devicelistscreen").refresh()

    def _refresh_transfers(self):
        self._screen("transferscreen").refresh()

    def _on_message(self, msg, peer):
        if peer == self.current_peer_id:
            self._screen("chatscreen").refresh()

    # ---- 导航 ----
    def open_chat(self, peer_id, name, address):
        self.current_peer_id = peer_id
        self.current_peer_name = name
        self.current_peer_address = address
        if self.session.link_for(peer_id) is None:
            self._ensure_connected(peer_id, address, name)
        self.root.ids.sm.current = "chatscreen"
        self._screen("chatscreen").refresh()

    def _ensure_connected(self, peer_id, address, name):
        async def go():
            try:
                await self.session.connect_peer(peer_id, address, name)
            except Exception as e:
                self._post(lambda: self.toast(f"连接失败: {e}"))
            else:
                self._post(self._refresh_devices)

        self.call_async(go())
