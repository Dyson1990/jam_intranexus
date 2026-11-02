"""赛博朋克主题：冷色霓虹（蓝紫 / 青）配色与发光控件。"""
from __future__ import annotations

from kivy.properties import ListProperty
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton

# 背景与面板
BG = (0.02, 0.04, 0.08, 1)
PANEL = (0.05, 0.09, 0.16, 1)
PANEL_LIGHT = (0.08, 0.13, 0.22, 1)
# 霓虹主色
CYAN = (0.0, 0.85, 1.0, 1)
MAGENTA = (0.65, 0.15, 1.0, 1)
BLUE = (0.2, 0.5, 1.0, 1)
# 文本
TEXT = (0.86, 0.93, 1.0, 1)
DIM = (0.45, 0.6, 0.75, 1)
DANGER = (1.0, 0.25, 0.45, 1)


class NeonButton(Button):
    """普通霓虹按钮：去掉默认背景，用主题色填充。"""

    accent = ListProperty(list(CYAN))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = PANEL_LIGHT
        self.color = TEXT
        self.bind(accent=self._tint)

    def _tint(self, *args):
        self.background_color = (*self.accent[:3], 0.35)


class NeonToggle(ToggleButton):
    """选中时在按钮背后绘制半透明发光层，形成霓虹光晕。"""

    accent = ListProperty(list(CYAN))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from kivy.graphics import Color, RoundedRectangle

        with self.canvas.before:
            self._glow_color = Color(*self.accent, a=0.0)
            self._glow = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
            self._bg_color = Color(*PANEL)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
        self.bind(state=self._redraw, pos=self._redraw, size=self._redraw, accent=self._redraw)
        self.background_normal = ""
        self.background_down = ""
        self.color = TEXT

    def _redraw(self, *args):
        active = self.state == "down"
        self._glow_color.rgba = [*self.accent, 0.28 if active else 0.0]
        self._bg_color.rgba = PANEL_LIGHT if active else PANEL
        self._glow.pos = (self.x - 3, self.y - 3)
        self._glow.size = (self.width + 6, self.height + 6)
        self._bg.pos = self.pos
        self._bg.size = self.size
