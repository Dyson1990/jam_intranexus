"""会话层集成测试：发现 → 连接握手 → 双向消息 → 文件传输（回环地址）。"""
import asyncio
import os

from core.session import Session
from core.messages import MessageStatus


def rand_id() -> bytes:
    return os.urandom(16)


async def wait_until(predicate, timeout: float = 5.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


async def _pair(tmp_path):
    a = Session(str(tmp_path / "a.db"), tcp_port=48120, discovery_port=48110,
                broadcast_interval=None, host="127.0.0.1")
    b = Session(str(tmp_path / "b.db"), tcp_port=48121, discovery_port=48111,
                broadcast_interval=None, host="127.0.0.1")
    await a.start()
    await b.start()
    return a, b


def test_discover_connect_and_text(tmp_path):
    async def run():
        a, b = await _pair(tmp_path)
        try:
            received = []
            b.on_message = lambda msg, peer: received.append((msg, peer))

            a.discovery.send_discover_to("127.0.0.1", b.discovery_port)
            await wait_until(lambda: any(p["device_id"] == b.device_id for p in a.peers()))

            await a.connect_peer(b.device_id, "127.0.0.1", tcp_port=b.tcp_port)
            await a.send_text(b.device_id, "你好，世界")

            await wait_until(lambda: len(received) == 1)
            assert received[0][0].text == "你好，世界"
            assert received[0][1] == a.device_id
            assert a.message_history(b.device_id)[0]["direction"] == "sent"
            assert b.message_history(a.device_id)[0]["direction"] == "received"
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(run())


def test_send_file(tmp_path):
    async def run():
        a, b = await _pair(tmp_path)
        recv_dir = tmp_path / "recv"
        b.set_save_dir(str(recv_dir))
        try:
            a.discovery.send_discover_to("127.0.0.1", b.discovery_port)
            await wait_until(lambda: any(p["device_id"] == b.device_id for p in a.peers()))
            await a.connect_peer(b.device_id, "127.0.0.1", tcp_port=b.tcp_port)

            src = tmp_path / "in.bin"
            data = os.urandom(200_000)
            src.write_bytes(data)

            await a.send_file(b.device_id, str(src))
            final = recv_dir / "in.bin"
            await wait_until(lambda: final.exists())
            assert final.read_bytes() == data
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(run())
