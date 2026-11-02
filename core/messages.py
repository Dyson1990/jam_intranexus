"""文本消息负载编解码与投递状态追踪。

TEXT 负载 = message_id(16B) + 时间戳(double) + UTF-8 文本；TEXT_ACK 负载 =
message_id(16B) + 状态(1B)。Messenger 绑定单条连接，发送后记录待确认消息，
收到 ACK 更新投递状态；收到 TEXT 自动回 ACK 并回调。
"""
from __future__ import annotations

import asyncio
import os
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

from .connection import Connection
from .protocol import Message, MsgType

TEXT_FMT = ">16sd"
TEXT_PREFIX_SIZE = struct.calcsize(TEXT_FMT)  # 24
ACK_FMT = ">16sB"


class MessageStatus(IntEnum):
    SENT = 1
    DELIVERED = 2
    FAILED = 3


@dataclass
class ChatMessage:
    message_id: bytes
    text: str
    sender_id: bytes | None = None
    status: int = MessageStatus.SENT


def encode_text(message_id: bytes, text: str, timestamp: float | None = None) -> bytes:
    if timestamp is None:
        timestamp = time.time()
    return struct.pack(TEXT_FMT, message_id, timestamp) + text.encode("utf-8")


def decode_text(payload: bytes) -> tuple[bytes, float, str]:
    message_id, timestamp = struct.unpack(TEXT_FMT, payload[:TEXT_PREFIX_SIZE])
    return message_id, timestamp, payload[TEXT_PREFIX_SIZE:].decode("utf-8", errors="replace")


def encode_ack(message_id: bytes, status: int) -> bytes:
    return struct.pack(ACK_FMT, message_id, int(status))


def decode_ack(payload: bytes) -> tuple[bytes, int]:
    message_id, status = struct.unpack(ACK_FMT, payload)
    return message_id, status


class Messenger:
    """单连接的文本消息收发与投递状态管理。"""

    def __init__(
        self,
        connection: Connection,
        on_text: Callable[[ChatMessage], None] | None = None,
        on_status: Callable[[ChatMessage], None] | None = None,
    ) -> None:
        self.connection = connection
        self.on_text = on_text
        self.on_status = on_status
        self._outgoing: dict[bytes, ChatMessage] = {}
        connection.on_message = self._handle

    async def send_text(self, text: str) -> ChatMessage:
        msg = ChatMessage(message_id=os.urandom(16), text=text, status=MessageStatus.SENT)
        self._outgoing[msg.message_id] = msg
        await self.connection.send(MsgType.TEXT, encode_text(msg.message_id, text))
        return msg

    def pending(self) -> list[ChatMessage]:
        return list(self._outgoing.values())

    def _handle(self, frame: Message) -> None:
        if frame.msg_type == MsgType.TEXT:
            message_id, _ts, text = decode_text(frame.payload)
            asyncio.get_running_loop().create_task(self._ack(message_id))
            if self.on_text is not None:
                self.on_text(ChatMessage(message_id=message_id, text=text, sender_id=frame.sender_id))
        elif frame.msg_type == MsgType.TEXT_ACK:
            message_id, status = decode_ack(frame.payload)
            msg = self._outgoing.get(message_id)
            if msg is not None:
                msg.status = status
                if self.on_status is not None:
                    self.on_status(msg)

    async def _ack(self, message_id: bytes) -> None:
        try:
            await self.connection.send(MsgType.TEXT_ACK, encode_ack(message_id, MessageStatus.DELIVERED))
        except ConnectionError:
            pass  # 连接已断，ACK 无意义
