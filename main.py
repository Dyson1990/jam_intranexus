"""入口：以 asyncio 驱动 Kivy 事件循环（网络与 GUI 共存）。"""
import asyncio

from ui.app import IntranexusApp


def main() -> None:
    asyncio.run(IntranexusApp().async_run(async_lib="asyncio"))


if __name__ == "__main__":
    main()
