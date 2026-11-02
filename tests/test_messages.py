import asyncio
import os

from core.connection import TCPServer, connect
from core.messages import (
    ChatMessage,
    MessageStatus,
    Messenger,
    decode_ack,
    decode_text,
    encode_ack,
    encode_text,
)
from core.protocol import MsgType


def rand_id() -> bytes:
    return os.urandom(16)


async def wait_until(predicate, timeout: float = 2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


def test_text_codec_roundtrip():
    mid = os.urandom(16)
    payload = encode_text(mid, "你好，世界")
    out_id, ts, text = decode_text(payload)
    assert out_id == mid
    assert text == "你好，世界"
    assert isinstance(ts, float)


def test_ack_codec_roundtrip():
    mid = os.urandom(16)
    out_id, status = decode_ack(encode_ack(mid, MessageStatus.DELIVERED))
    assert out_id == mid
    assert status == MessageStatus.DELIVERED


def test_bidirectional_text_with_delivery_status():
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48200)
        await server.start()
        try:
            conn = await connect(rand_id(), "127.0.0.1", 48200, heartbeat_interval=None)
            await wait_until(lambda: len(server.connections) == 1)
            sconn = next(iter(server.connections))

            client_texts: list[ChatMessage] = []
            server_texts: list[ChatMessage] = []
            client_status: list[ChatMessage] = []
            server_status: list[ChatMessage] = []
            client = Messenger(conn, on_text=client_texts.append, on_status=client_status.append)
            server_messenger = Messenger(sconn, on_text=server_texts.append, on_status=server_status.append)

            await client.send_text("hi")
            await wait_until(lambda: len(server_texts) == 1)
            assert server_texts[0].text == "hi"
            assert server_texts[0].sender_id == conn.local_device_id
            await wait_until(lambda: len(client_status) == 1)
            assert client_status[0].status == MessageStatus.DELIVERED

            await server_messenger.send_text("hello back")
            await wait_until(lambda: len(client_texts) == 1)
            assert client_texts[0].text == "hello back"
            await wait_until(lambda: len(server_status) == 1)
            assert server_status[0].status == MessageStatus.DELIVERED

            conn.close()
        finally:
            await server.stop()

    asyncio.run(run())
