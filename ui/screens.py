"""四大页面：设备列表 / 聊天 / 文件传输 / 设置。

各页面经 ``App.get_running_app().session`` 访问后端；网络结果由 App 的 on_* 分发，
再经 ``Clock.schedule_once`` 回到 Kivy 线程刷新（回调均在事件循环线程内触发）。
"""
from __future__ import annotations

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from platform import default_name, default_save_dir, pick_directory, pick_file
from .theme import CYAN, DANGER, DIM, MAGENTA, PANEL, TEXT, NeonButton


def _app() -> App:
    return App.get_running_app()


def _title(text: str) -> Label:
    return Label(text=text, font_size="22sp", bold=True, color=CYAN,
                 size_hint_y=None, height="48dp", halign="left", valign="middle")


def _scroll_box() -> tuple[ScrollView, BoxLayout]:
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing="8dp", padding="4dp")
    box.bind(minimum_height=box.setter("height"))
    scroll = ScrollView()
    scroll.add_widget(box)
    return scroll, box


def _input(text: str, hint: str) -> TextInput:
    inp = TextInput(text=text, hint_text=hint, multiline=False,
                    size_hint_y=None, height="44dp", background_color=PANEL,
                    foreground_color=TEXT, cursor_color=CYAN)
    return inp


class DeviceListScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding="16dp", spacing="12dp")
        root.add_widget(_title("设备"))
        self.scroll, self.list_box = _scroll_box()
        root.add_widget(self.scroll)

        bar = BoxLayout(orientation="horizontal", size_hint_y=None, height="48dp", spacing="8dp")
        self.ip_input = TextInput(hint_text="输入 IP 地址", multiline=False, size_hint_x=1,
                                  background_color=PANEL, foreground_color=TEXT, cursor_color=CYAN)
        probe = NeonButton(text="探测", accent=MAGENTA, size_hint_x=None, width="80dp")
        probe.bind(on_release=lambda b: self._probe())
        refresh = NeonButton(text="刷新", size_hint_x=None, width="80dp")
        refresh.bind(on_release=lambda b: self._broadcast())
        bar.add_widget(self.ip_input)
        bar.add_widget(probe)
        bar.add_widget(refresh)
        root.add_widget(bar)
        self.add_widget(root)

    def _broadcast(self):
        s = _app().session
        s.discovery.broadcast()
        self.refresh()

    def _probe(self):
        ip = self.ip_input.text.strip()
        if not ip:
            return
        _app().session.manual_discover(ip)

    def refresh(self, *args):
        s = _app().session
        self.list_box.clear_widgets()
        peers = s.peers()
        if not peers:
            self.list_box.add_widget(Label(text="未发现设备，点「刷新」或输入 IP 点「探测」",
                                           color=DIM, size_hint_y=None, height="44dp"))
            return
        for p in peers:
            status = "已连接" if p["connected"] else "在线"
            color = MAGENTA if p["connected"] else TEXT
            btn = NeonButton(text=f"{p['name']}   {p['address']}   {status}",
                             size_hint_y=None, height="56dp", halign="left", color=color)
            btn.bind(on_release=lambda b, p=p: _app().open_chat(p["device_id"], p["name"], p["address"]))
            self.list_box.add_widget(btn)


class ChatScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding="16dp", spacing="12dp")
        self.title_label = _title("消息")
        root.add_widget(self.title_label)
        self.scroll, self.msg_box = _scroll_box()
        root.add_widget(self.scroll)

        bar = BoxLayout(orientation="horizontal", size_hint_y=None, height="48dp", spacing="8dp")
        self.input = TextInput(hint_text="输入消息", multiline=False, size_hint_x=1,
                               background_color=PANEL, foreground_color=TEXT, cursor_color=CYAN)
        send = NeonButton(text="发送", size_hint_x=None, width="90dp")
        send.bind(on_release=lambda b: self._send())
        bar.add_widget(self.input)
        bar.add_widget(send)
        root.add_widget(bar)
        self.add_widget(root)

    def refresh(self, *args):
        app = _app()
        s = app.session
        self.title_label.text = app.current_peer_name or "消息"
        self.msg_box.clear_widgets()
        peer = app.current_peer_id
        if peer is None:
            self.msg_box.add_widget(Label(text="在「设备」页选择设备开始聊天", color=DIM,
                                          size_hint_y=None, height="44dp"))
            return
        for m in s.message_history(peer):
            self._bubble(m)

    def _bubble(self, m: dict):
        mine = m["direction"] == "sent"
        prefix = "我" if mine else _app().current_peer_name
        color = CYAN if mine else TEXT
        status = {1: "✓", 2: "✓✓", 3: "✗"}.get(m["status"], "")
        label = Label(text=f"{prefix}: {m['text']}  {status}", color=color, size_hint_y=None,
                      height="36dp", halign="left", valign="middle", font_size="15sp")
        label.bind(size=lambda *a: setattr(label, "text_size", (label.width, None)))
        self.msg_box.add_widget(label)

    def _send(self):
        app = _app()
        text = self.input.text.strip()
        peer = app.current_peer_id
        if not text or peer is None:
            return
        self.input.text = ""

        async def go():
            try:
                await app.session.send_text(peer, text)
            except Exception as e:
                app._post(lambda: app.toast(f"发送失败: {e}"))

        app.call_async(go())


class TransferScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding="16dp", spacing="12dp")
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height="48dp", spacing="8dp")
        header.add_widget(_title("传输"))
        send_btn = NeonButton(text="发送文件", accent=MAGENTA, size_hint_x=None, width="120dp")
        send_btn.bind(on_release=lambda b: self._send_file())
        header.add_widget(send_btn)
        root.add_widget(header)
        self.scroll, self.list_box = _scroll_box()
        root.add_widget(self.scroll)
        self.add_widget(root)

    def refresh(self, *args):
        s = _app().session
        self.list_box.clear_widgets()
        transfers = s.active_transfers()
        if not transfers:
            self.list_box.add_widget(Label(text="暂无传输任务", color=DIM,
                                           size_hint_y=None, height="44dp"))
            return
        for t in transfers:
            self.list_box.add_widget(self._row(t))

    def _row(self, t: dict):
        row = BoxLayout(orientation="vertical", size_hint_y=None, height="100dp", spacing="2dp")
        direction = "发送" if t["direction"] == "send" else "接收"
        off_kb, size_kb = t["offset"] / 1024, t["size"] / 1024
        if t["status"] == "active":
            line = f"{direction}  {t['name']}  ·  {off_kb:.0f}/{size_kb:.0f} KB  ·  {t['speed']/1024:.0f} KB/s"
        else:
            line = f"{direction}  {t['name']}  ·  {t['status']}"
        lbl = Label(text=line, color=TEXT, size_hint_y=None, height="26dp", halign="left",
                    valign="middle", font_size="13sp")
        lbl.bind(size=lambda *a: setattr(lbl, "text_size", (lbl.width, None)))
        pb = ProgressBar(max=1.0, value=t["offset"] / max(t["size"], 1), size_hint_y=None, height="12dp")
        row.add_widget(lbl)
        row.add_widget(pb)
        if t["status"] == "active":
            cancel = NeonButton(text="取消", accent=DANGER, size_hint_y=None, height="40dp",
                                size_hint_x=None, width="120dp")
            cancel.bind(on_release=lambda b, f=t["file_id"]: self._cancel(f))
            row.add_widget(cancel)
        return row

    def _cancel(self, file_id: bytes):
        _app().session.cancel_transfer(file_id)

    def _send_file(self):
        app = _app()
        peer = app.current_peer_id
        if peer is None:
            app.toast("先在「设备」页选择设备")
            return

        def got(path):
            async def go():
                try:
                    await app.session.send_file(peer, path)
                except Exception as e:
                    app._post(lambda: app.toast(f"发送失败: {e}"))
            app.call_async(go())

        pick_file(got)


class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding="16dp", spacing="12dp")
        root.add_widget(_title("设置"))

        self.name_input = _input("", "设备名")
        self.dir_input = _input("", "保存目录")

        name_lbl = Label(text="设备名", color=DIM, size_hint_y=None, height="24dp", halign="left")
        dir_lbl = Label(text="保存目录", color=DIM, size_hint_y=None, height="24dp", halign="left")
        root.add_widget(name_lbl)
        root.add_widget(self.name_input)

        dir_row = BoxLayout(orientation="horizontal", size_hint_y=None, height="44dp", spacing="8dp")
        browse = NeonButton(text="浏览", size_hint_x=None, width="90dp")
        browse.bind(on_release=lambda b: pick_directory(lambda p: setattr(self.dir_input, "text", p)))
        dir_row.add_widget(self.dir_input)
        dir_row.add_widget(browse)
        root.add_widget(dir_lbl)
        root.add_widget(dir_row)

        save_btn = NeonButton(text="保存设置", size_hint_y=None, height="52dp")
        save_btn.bind(on_release=lambda b: self._save())
        root.add_widget(save_btn)

        clear_btn = NeonButton(text="清空本地数据", accent=DANGER, size_hint_y=None, height="52dp")
        clear_btn.bind(on_release=lambda b: self._confirm_clear())
        root.add_widget(clear_btn)

        root.add_widget(Label(text="", size_hint_y=1))
        self.add_widget(root)

    def refresh(self, *args):
        s = _app().session
        self.name_input.text = s.name
        self.dir_input.text = s.save_dir

    def _save(self):
        app = _app()
        app.session.set_name(self.name_input.text.strip() or default_name())
        app.session.set_save_dir(self.dir_input.text.strip() or default_save_dir())
        app.toast("已保存")

    def _confirm_clear(self):
        app = _app()
        content = BoxLayout(orientation="vertical", padding="12dp", spacing="12dp")
        content.add_widget(Label(text="确定清空全部本地数据？\n（设备 / 消息 / 传输记录 / 设置）",
                                 color=DANGER, halign="center"))
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height="52dp", spacing="12dp")
        ok = NeonButton(text="清空", accent=DANGER)
        cancel = NeonButton(text="取消")
        popup = Popup(title="确认", content=content, size_hint=(0.85, 0.4))
        ok.bind(on_release=lambda b: self._do_clear(popup))
        cancel.bind(on_release=lambda b: popup.dismiss())
        row.add_widget(ok)
        row.add_widget(cancel)
        content.add_widget(row)
        popup.open()

    def _do_clear(self, popup):
        popup.dismiss()
        app = _app()
        app.session.clear_data()
        self.refresh()
        app.toast("已清空")
