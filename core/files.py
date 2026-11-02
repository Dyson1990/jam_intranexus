"""文件分块传输：OFFER/ACCEPT 协商偏移断点续传，SHA-256 校验后落地，支持取消。

流程：发送方 OFFER(文件ID/名/大小/SHA-256) → 接收方 ACCEPT(已收偏移) →
发送方从偏移处起发 CHUNK → 发送方 COMPLETE(全文件 SHA-256) → 接收方校验后落盘。
文件 I/O 全部经 ``asyncio.to_thread`` 执行，避免阻塞事件循环。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import struct
from typing import Callable

from .connection import Connection
from .protocol import Message, MsgType

CHUNK_SIZE = 64 * 1024
FILE_ID_SIZE = 16
SHA256_SIZE = 32

OFFER_FMT = ">16sQ32s"       # file_id, size, sha256（名称 UTF-8 追加）
ACCEPT_FMT = ">16sQ"         # file_id, offset
CHUNK_FMT = ">16sQ"          # file_id, offset（数据追加）
COMPLETE_FMT = ">16s32s"     # file_id, sha256
CANCEL_FMT = ">16s"          # file_id

_OFFER_PREFIX = struct.calcsize(OFFER_FMT)
_CHUNK_PREFIX = struct.calcsize(CHUNK_FMT)


def encode_offer(file_id: bytes, name: str, size: int, sha256: bytes) -> bytes:
    return struct.pack(OFFER_FMT, file_id, size, sha256) + name.encode("utf-8")


def decode_offer(payload: bytes) -> tuple[bytes, str, int, bytes]:
    file_id, size, sha256 = struct.unpack(OFFER_FMT, payload[:_OFFER_PREFIX])
    name = payload[_OFFER_PREFIX:].decode("utf-8", errors="replace")
    return file_id, name, size, sha256


def encode_accept(file_id: bytes, offset: int) -> bytes:
    return struct.pack(ACCEPT_FMT, file_id, offset)


def decode_accept(payload: bytes) -> tuple[bytes, int]:
    return struct.unpack(ACCEPT_FMT, payload)


def encode_chunk(file_id: bytes, offset: int, data: bytes) -> bytes:
    return struct.pack(CHUNK_FMT, file_id, offset) + data


def decode_chunk(payload: bytes) -> tuple[bytes, int, bytes]:
    file_id, offset = struct.unpack(CHUNK_FMT, payload[:_CHUNK_PREFIX])
    return file_id, offset, payload[_CHUNK_PREFIX:]


def encode_complete(file_id: bytes, sha256: bytes) -> bytes:
    return struct.pack(COMPLETE_FMT, file_id, sha256)


def decode_complete(payload: bytes) -> tuple[bytes, bytes]:
    return struct.unpack(COMPLETE_FMT, payload)


def encode_cancel(file_id: bytes) -> bytes:
    return struct.pack(CANCEL_FMT, file_id)


def decode_cancel(payload: bytes) -> bytes:
    return struct.unpack(CANCEL_FMT, payload)[0]


def _file_meta(path: str) -> tuple[int, bytes]:
    """单遍读取计算大小与 SHA-256（阻塞，须在 executor 中调用）。"""
    sha = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK_SIZE)
            if not block:
                break
            size += len(block)
            sha.update(block)
    return size, sha.digest()


class FileSender:
    """发送单个文件；``run()`` 完成后 ``finished``/``cancelled`` 反映结果。"""

    def __init__(
        self,
        connection: Connection,
        path: str,
        file_id: bytes | None = None,
        chunk_size: int = CHUNK_SIZE,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        self.connection = connection
        self.path = path
        self.file_id = file_id or os.urandom(FILE_ID_SIZE)
        self.chunk_size = chunk_size
        self.on_progress = on_progress
        self.cancelled = False
        self.finished = False
        self._accept_future: asyncio.Future | None = None

    def _handle_accept(self, offset: int) -> None:
        if self._accept_future is not None and not self._accept_future.done():
            self._accept_future.set_result(offset)

    def _handle_cancel(self) -> None:
        self.cancelled = True
        if self._accept_future is not None and not self._accept_future.done():
            self._accept_future.set_result(0)

    def cancel(self) -> None:
        self.cancelled = True
        if self._accept_future is not None and not self._accept_future.done():
            self._accept_future.set_result(0)
        try:
            asyncio.get_running_loop().create_task(self._send_cancel())
        except RuntimeError:
            pass  # 无运行中的事件循环（同步调用）时不通知，仅本地停止

    async def _send_cancel(self) -> None:
        try:
            await self.connection.send(MsgType.FILE_CANCEL, encode_cancel(self.file_id))
        except ConnectionError:
            pass

    async def run(self, accept_timeout: float = 30.0) -> None:
        self._accept_future = asyncio.get_running_loop().create_future()
        if self.cancelled:
            return
        size, sha256 = await asyncio.to_thread(_file_meta, self.path)
        name = os.path.basename(self.path)
        await self.connection.send(MsgType.FILE_OFFER, encode_offer(self.file_id, name, size, sha256))
        offset = await asyncio.wait_for(self._accept_future, timeout=accept_timeout)
        if self.cancelled:
            return
        await self._stream(offset, size)
        if not self.cancelled:
            await self.connection.send(MsgType.FILE_COMPLETE, encode_complete(self.file_id, sha256))
            self.finished = True

    async def _stream(self, offset: int, size: int) -> None:
        sent = offset
        with open(self.path, "rb") as f:
            f.seek(offset)
            while sent < size and not self.cancelled:
                data = await asyncio.to_thread(f.read, self.chunk_size)
                if not data:
                    break
                await self.connection.send(MsgType.FILE_CHUNK, encode_chunk(self.file_id, sent, data))
                sent += len(data)
                if self.on_progress is not None:
                    self.on_progress(sent, size)


class FileReceiver:
    """接收单个文件，按偏移续传，校验通过后从 ``.part`` 落地为最终文件。"""

    def __init__(
        self,
        connection: Connection,
        save_dir: str,
        file_id: bytes,
        name: str,
        size: int,
        sha256: bytes,
        offset: int = 0,
        on_progress: Callable[[int, int], None] | None = None,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        self.connection = connection
        self.save_dir = save_dir
        self.file_id = file_id
        self.name = name
        self.size = size
        self.expected_sha256 = sha256
        self.offset = offset
        self.on_progress = on_progress
        self.on_done = on_done
        self.finished = False
        self.cancelled = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._completed = False
        self._sha = hashlib.sha256()
        self._final_path = os.path.join(save_dir, name)
        self._tmp_path = self._final_path + ".part"

    def _handle_chunk(self, frame: Message) -> None:
        file_id, offset, data = decode_chunk(frame.payload)
        if file_id != self.file_id:
            return
        # 不在此处校验偏移：该回调在接收循环内同步触发，而 self.offset 由
        # 独立的写入任务更新，校验放写入循环内保证一致性。
        self._queue.put_nowait((offset, data))

    def _handle_complete(self, frame: Message) -> None:
        file_id, _sha = decode_complete(frame.payload)
        if file_id != self.file_id:
            return
        self._completed = True
        self._queue.put_nowait(None)

    def _handle_cancel(self) -> None:
        self.cancelled = True
        self._queue.put_nowait(None)

    def cancel(self) -> None:
        """本地主动取消接收，并通知发送方停止。"""
        self.cancelled = True
        self._queue.put_nowait(None)
        try:
            asyncio.get_running_loop().create_task(self._send_cancel())
        except RuntimeError:
            pass  # 无事件循环（测试同步路径）时仅本地停止

    async def _send_cancel(self) -> None:
        try:
            await self.connection.send(MsgType.FILE_CANCEL, encode_cancel(self.file_id))
        except (ConnectionError, AttributeError):
            pass  # 连接已断或无连接（测试）

    async def run(self) -> None:
        os.makedirs(self.save_dir, exist_ok=True)
        mode = "r+b" if self.offset > 0 else "w+b"
        with open(self._tmp_path, mode) as f:
            if self.offset > 0:
                self._sha = await asyncio.to_thread(_seed_hash, self._tmp_path, self.offset)
            while True:
                item = await self._queue.get()
                if item is None:
                    break
                offset, data = item
                if offset != self.offset:
                    continue  # 防御：跳过乱序/重复，TCP 顺序下不应发生
                await asyncio.to_thread(_write_at, f, offset, data)
                self._sha.update(data)
                self.offset += len(data)
                if self.on_progress is not None:
                    self.on_progress(self.offset, self.size)
        if self.cancelled:
            return  # 保留 .part 供下次续传
        if not self._completed or self.offset != self.size:
            return  # 连接中断或未收齐，保留 .part
        if self._sha.digest() != self.expected_sha256:
            return  # 校验失败，不落地
        os.replace(self._tmp_path, self._final_path)
        self.finished = True
        if self.on_done is not None:
            self.on_done(self._final_path)


def _write_at(f, offset: int, data: bytes) -> None:
    f.seek(offset)
    f.write(data)
    f.flush()


def _seed_hash(path: str, n: int) -> hashlib.sha256:
    sha = hashlib.sha256()
    remaining = n
    with open(path, "rb") as f:
        while remaining > 0:
            block = f.read(min(CHUNK_SIZE, remaining))
            if not block:
                break
            sha.update(block)
            remaining -= len(block)
    return sha


class FileTransfer:
    """挂在单条连接上的文件传输入口：发送文件 + 接收入站 OFFER。"""

    def __init__(self, connection: Connection, save_dir: str | None = None) -> None:
        self.connection = connection
        self.save_dir = save_dir
        self.on_incoming: Callable[[FileReceiver], None] | None = None
        self._senders: dict[bytes, FileSender] = {}
        self._receivers: dict[bytes, FileReceiver] = {}
        connection.router.register(MsgType.FILE_OFFER, self._on_offer)
        connection.router.register(MsgType.FILE_ACCEPT, self._on_accept)
        connection.router.register(MsgType.FILE_CHUNK, self._on_chunk)
        connection.router.register(MsgType.FILE_COMPLETE, self._on_complete)
        connection.router.register(MsgType.FILE_CANCEL, self._on_cancel)

    async def send_file(
        self,
        path: str,
        chunk_size: int = CHUNK_SIZE,
        on_progress: Callable[[int, int], None] | None = None,
        file_id: bytes | None = None,
    ) -> FileSender:
        sender = FileSender(self.connection, path, file_id=file_id, chunk_size=chunk_size, on_progress=on_progress)
        self._senders[sender.file_id] = sender
        try:
            await sender.run()
        finally:
            self._senders.pop(sender.file_id, None)
        return sender

    def _on_offer(self, frame: Message) -> None:
        if self.save_dir is None:
            return  # 未配置接收目录，拒绝入站文件
        file_id, name, size, sha256 = decode_offer(frame.payload)
        offset = _resume_offset(self.save_dir, name, size)
        receiver = FileReceiver(self.connection, self.save_dir, file_id, name, size, sha256, offset)
        self._receivers[file_id] = receiver
        asyncio.get_running_loop().create_task(receiver.run())
        asyncio.get_running_loop().create_task(
            self.connection.send(MsgType.FILE_ACCEPT, encode_accept(file_id, offset))
        )
        if self.on_incoming is not None:
            self.on_incoming(receiver)

    def _on_accept(self, frame: Message) -> None:
        file_id, offset = decode_accept(frame.payload)
        sender = self._senders.get(file_id)
        if sender is not None:
            sender._handle_accept(offset)

    def _on_chunk(self, frame: Message) -> None:
        file_id = decode_chunk(frame.payload)[0]
        receiver = self._receivers.get(file_id)
        if receiver is not None:
            receiver._handle_chunk(frame)

    def _on_complete(self, frame: Message) -> None:
        file_id = decode_complete(frame.payload)[0]
        receiver = self._receivers.get(file_id)
        if receiver is not None:
            receiver._handle_complete(frame)

    def _on_cancel(self, frame: Message) -> None:
        file_id = decode_cancel(frame.payload)
        sender = self._senders.get(file_id)
        if sender is not None:
            sender._handle_cancel()
        receiver = self._receivers.get(file_id)
        if receiver is not None:
            receiver._handle_cancel()


def _resume_offset(save_dir: str, name: str, size: int) -> int:
    """已有 ``.part`` 文件则以其大小为续传偏移（截断到不超过目标大小）。"""
    part = os.path.join(save_dir, name + ".part")
    if os.path.exists(part):
        return min(os.path.getsize(part), size)
    return 0
