"""异步 TCP 连接管理：帧收发、心跳、断线检测与按类型消息分发。

每个 Connection 对应一条已建立的 TCP 连接，内部跑接收循环；心跳循环按周期发
PING 并在超时未收到 PONG 时判定断线。断线（对端关闭或心跳超时）统一触发
``on_close``。业务层通过 ``Router`` 按消息类型注册处理器。
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Callable

from .crypto import FrameCipher
from .protocol import HEADER_SIZE, Message, MsgType, ProtocolError, parse_header

TCP_PORT = 47900

log = logging.getLogger("connection")


class Router:
    """按消息类型分发到注册的处理器（同一类型可有多个）。"""

    def __init__(self) -> None:
        self._handlers: dict[int, list[Callable[[Message], None]]] = {}

    def register(self, msg_type: int, handler: Callable[[Message], None]) -> None:
        self._handlers.setdefault(msg_type, []).append(handler)

    def dispatch(self, msg: Message) -> None:
        for handler in self._handlers.get(msg.msg_type, ()):
            handler(msg)


class Connection:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        local_device_id: bytes,
        peer_id: bytes | None = None,
        heartbeat_interval: float | None = 10.0,
        heartbeat_timeout: float = 30.0,
        cipher: FrameCipher | None = None,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.local_device_id = local_device_id
        self.peer_id = peer_id
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.cipher = cipher
        self.router = Router()
        self.on_close: Callable[[], None] | None = None
        self._last_pong = time.monotonic()
        self._closed = False
        self._recv_task: asyncio.Task | None = None
        self._hb_task: asyncio.Task | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    def start(self) -> None:
        """启动接收循环（及可选心跳），由内部任务驱动。"""
        self._recv_task = asyncio.create_task(self._recv_loop())
        if self.heartbeat_interval is not None:
            self._hb_task = asyncio.create_task(self._heartbeat_loop())

    async def read_message(self) -> Message:
        if self.cipher is not None:
            # 加密态：整帧加密后以 4 字节长度前缀分帧，头/负载一并保密
            (n,) = struct.unpack(">I", await self.reader.readexactly(4))
            ciphertext = await self.reader.readexactly(n)
            return Message.decode(self.cipher.decrypt(ciphertext))
        header = await self.reader.readexactly(HEADER_SIZE)
        _, _, _, _, payload_len = parse_header(header)
        payload = await self.reader.readexactly(payload_len)
        return Message.decode(header + payload)

    async def send(self, msg_type: int, payload: bytes = b"") -> None:
        await self.send_message(Message(self.local_device_id, msg_type, payload))

    async def send_message(self, msg: Message) -> None:
        if self._closed:
            raise ConnectionError("connection closed")
        if self.cipher is not None:
            data = self.cipher.encrypt(msg.encode())
            self.writer.write(struct.pack(">I", len(data)) + data)
        else:
            self.writer.write(msg.encode())
        await self.writer.drain()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.writer.close()
        if self._recv_task is not None:
            self._recv_task.cancel()
        if self._hb_task is not None:
            self._hb_task.cancel()
        if self.on_close is not None:
            self.on_close()

    async def wait_closed(self) -> None:
        if self._recv_task is not None:
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _recv_loop(self) -> None:
        while not self._closed:
            try:
                msg = await self.read_message()
            except ValueError:
                log.warning("decryption/auth failed, closing connection")
                break
            except (asyncio.IncompleteReadError, ConnectionError, OSError, ProtocolError):
                break
            if msg.msg_type == MsgType.PING:
                await self.send(MsgType.PONG)
            elif msg.msg_type == MsgType.PONG:
                self._last_pong = time.monotonic()
            else:
                self.router.dispatch(msg)
        self.close()

    async def _heartbeat_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self.heartbeat_interval)
            if self._closed:
                return
            await self.send(MsgType.PING)
            if time.monotonic() - self._last_pong > self.heartbeat_timeout:
                self.close()


class TCPServer:
    """接受入站 TCP 连接，管理活跃 Connection 集合。"""

    def __init__(self, device_id: bytes, host: str = "0.0.0.0", port: int = TCP_PORT) -> None:
        self.device_id = device_id
        self.host = host
        self.port = port
        self.on_connect: Callable[[Connection], None] | None = None
        self.on_close: Callable[[Connection], None] | None = None
        self.connections: set[Connection] = set()
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._on_connect, self.host, self.port)

    async def stop(self) -> None:
        for conn in list(self.connections):
            conn.close()
        self.connections.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn = Connection(reader, writer, self.device_id)
        if self.on_connect is not None:
            self.on_connect(conn)
        conn.on_close = lambda: self._on_conn_close(conn)
        self.connections.add(conn)
        conn.start()
        await conn.wait_closed()
        self.connections.discard(conn)

    def _on_conn_close(self, conn: Connection) -> None:
        self.connections.discard(conn)
        if self.on_close is not None:
            self.on_close(conn)


async def connect(
    local_device_id: bytes,
    host: str,
    port: int = TCP_PORT,
    heartbeat_interval: float | None = 10.0,
    heartbeat_timeout: float = 30.0,
    cipher: FrameCipher | None = None,
) -> Connection:
    """作为客户端建连，返回已启动的 Connection。"""
    reader, writer = await asyncio.open_connection(host, port)
    conn = Connection(reader, writer, local_device_id,
                      heartbeat_interval=heartbeat_interval, heartbeat_timeout=heartbeat_timeout,
                      cipher=cipher)
    conn.start()
    return conn
