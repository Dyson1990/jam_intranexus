import asyncio
import os

from core.connection import TCPServer, connect
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


def test_connect_and_bidirectional_message():
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48100)
        await server.start()
        try:
            conn = await connect(rand_id(), "127.0.0.1", 48100, heartbeat_interval=None)
            await wait_until(lambda: len(server.connections) == 1)
            sconn = next(iter(server.connections))

            received: list[bytes] = []
            conn.router.register(MsgType.TEXT, lambda m: received.append(m.payload))
            await sconn.send(MsgType.TEXT, b"hello-from-server")
            await wait_until(lambda: len(received) == 1)
            assert received[0] == b"hello-from-server"

            # 反向：客户端发给服务端
            sreceived: list[bytes] = []
            sconn.router.register(MsgType.TEXT, lambda m: sreceived.append(m.payload))
            await conn.send(MsgType.TEXT, b"hello-from-client")
            await wait_until(lambda: len(sreceived) == 1)
            assert sreceived[0] == b"hello-from-client"
            conn.close()
        finally:
            await server.stop()

    asyncio.run(run())


def test_ping_pong_auto_reply():
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48101)
        await server.start()
        try:
            conn = await connect(rand_id(), "127.0.0.1", 48101, heartbeat_interval=None)
            await wait_until(lambda: len(server.connections) == 1)
            conn._last_pong = 0.0
            await conn.send(MsgType.PING)
            await wait_until(lambda: conn._last_pong != 0.0)
            conn.close()
        finally:
            await server.stop()

    asyncio.run(run())


def test_disconnect_detected_on_server():
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48102)
        await server.start()
        closed = asyncio.Event()
        server.on_close = lambda c: closed.set()
        conn = await connect(rand_id(), "127.0.0.1", 48102, heartbeat_interval=None)
        await wait_until(lambda: len(server.connections) == 1)
        conn.close()
        await wait_until(lambda: closed.is_set())
        assert len(server.connections) == 0
        await server.stop()

    asyncio.run(run())


def test_heartbeat_timeout_detects_dead_peer():
    async def run():
        # 哑服务端：接受连接但不回 PONG，模拟对端失联
        async def dumb(reader, writer):
            await reader.read()
            writer.close()

        server = await asyncio.start_server(dumb, "127.0.0.1", 48103)
        try:
            closed = asyncio.Event()
            conn = await connect(rand_id(), "127.0.0.1", 48103, heartbeat_interval=0.05, heartbeat_timeout=0.1)
            conn.on_close = lambda: closed.set()
            await wait_until(lambda: closed.is_set(), timeout=1.0)
            assert conn.closed
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(run())
