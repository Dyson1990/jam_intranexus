"""Kivy 应用：赛博朋克主题 + 四大页面导航。"""
from __future__ import annotations

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout

from .screens import ChatScreen, DeviceListScreen, SettingsScreen, TransferScreen
from .theme import BLUE, CYAN, DIM, MAGENTA, PANEL, PANEL_LIGHT, TEXT

KV = """
#:import BG ui.theme.BG
#:import PANEL ui.theme.PANEL
#:import CYAN ui.theme.CYAN
#:import MAGENTA ui.theme.MAGENTA
#:import TEXT ui.theme.TEXT
#:import DIM ui.theme.DIM

<ScreenTitle@Label>:
    font_size: '22sp'
    bold: True
    color: CYAN
    size_hint_y: None
    height: '48dp'
    halign: 'left'
    text_size: self.size

<Placeholder@Label>:
    color: DIM
    font_size: '16sp'
    halign: 'center'
    valign: 'middle'

<DeviceListScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '16dp'
        spacing: '12dp'
        ScreenTitle:
            text: '设备'
        Placeholder:
            text: '局域网设备将在此显示'

<ChatScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '16dp'
        spacing: '12dp'
        ScreenTitle:
            text: '消息'
        Placeholder:
            text: '选择设备开始聊天'

<TransferScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '16dp'
        spacing: '12dp'
        ScreenTitle:
            text: '传输'
        Placeholder:
            text: '文件传输任务将在此显示'

<SettingsScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '16dp'
        spacing: '12dp'
        ScreenTitle:
            text: '设置'
        Placeholder:
            text: '设备名 / 保存目录 / 配对密钥'

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
        ChatScreen:
        TransferScreen:
        SettingsScreen:
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
        Builder.load_string(KV)
        return RootWidget()
