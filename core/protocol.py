"""二进制协议：固定头 + 变长负载，用于 TCP 流式分帧与 UDP 单包。

帧结构（网络字节序）::

    magic(4s) version(1B) type(1B) flags(1B) sender_id(16s) payload_len(4B) | payload

头部共 27 字节；负载长度上限 MAX_PAYLOAD，超限视为协议错误。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

MAGIC = b"JINX"
VERSION = 1
HEADER_FMT = ">4sBBB16sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 27
MAX_PAYLOAD = 1 << 20  # 1 MiB
DEVICE_ID_SIZE = 16


class MsgType(IntEnum):
    """消息类型，取值按用途分区，避免与后续扩展冲突。"""
    DISCOVER = 0x01        # UDP 广播：寻找在线设备
    PRESENCE = 0x02        # UDP 应答 / 周期性在线声明
    PAIR_REQUEST = 0x03
    PAIR_RESPONSE = 0x04
    TEXT = 0x10            # 文本消息
    TEXT_ACK = 0x11        # 文本投递状态
    FILE_OFFER = 0x20
    FILE_ACCEPT = 0x21     # 含已接收偏移量，用于断点续传
    FILE_CHUNK = 0x22
    FILE_CHUNK_ACK = 0x23
    FILE_COMPLETE = 0x24
    FILE_CANCEL = 0x25
    PING = 0xF0
    PONG = 0xF1
    ERROR = 0x7F


class ErrorCode(IntEnum):
    OK = 0
    UNKNOWN_TYPE = 1
    INVALID_LENGTH = 2
    BAD_HEADER = 3
    AUTH_REQUIRED = 4
    AUTH_FAILED = 5
    CHECKSUM_MISMATCH = 6
    NOT_FOUND = 7
    UNSUPPORTED = 8


class ProtocolError(Exception):
    """协议编解码错误，携带错误码便于对端回传 ERROR 帧。"""

    def __init__(self, code: int, detail: str = "") -> None:
        self.code = ErrorCode(code)
        self.detail = detail
        super().__init__(f"{self.code.name}: {detail}" if detail else self.code.name)


@dataclass(frozen=True)
class Message:
    sender_id: bytes
    msg_type: int
    payload: bytes = b""
    flags: int = 0
    version: int = VERSION

    def __post_init__(self) -> None:
        if len(self.sender_id) != DEVICE_ID_SIZE:
            raise ProtocolError(ErrorCode.BAD_HEADER, f"device id must be {DEVICE_ID_SIZE} bytes")
        if len(self.payload) > MAX_PAYLOAD:
            raise ProtocolError(ErrorCode.INVALID_LENGTH, "payload exceeds MAX_PAYLOAD")

    def encode(self) -> bytes:
        header = struct.pack(
            HEADER_FMT, MAGIC, self.version, self.msg_type, self.flags,
            self.sender_id, len(self.payload),
        )
        return header + self.payload

    @classmethod
    def decode(cls, data: bytes) -> "Message":
        if len(data) < HEADER_SIZE:
            raise ProtocolError(ErrorCode.INVALID_LENGTH, "frame shorter than header")
        magic, version, msg_type, flags, sender_id, payload_len = struct.unpack(
            HEADER_FMT, data[:HEADER_SIZE]
        )
        if magic != MAGIC:
            raise ProtocolError(ErrorCode.BAD_HEADER, "bad magic")
        if version != VERSION:
            raise ProtocolError(ErrorCode.BAD_HEADER, f"unsupported version {version}")
        if payload_len > MAX_PAYLOAD:
            raise ProtocolError(ErrorCode.INVALID_LENGTH, f"payload_len {payload_len} exceeds max")
        if len(data) != HEADER_SIZE + payload_len:
            raise ProtocolError(ErrorCode.INVALID_LENGTH, "frame length mismatch")
        return cls(sender_id=sender_id, msg_type=msg_type, payload=data[HEADER_SIZE:], flags=flags, version=version)


def build_error_payload(code: int, detail: str = "") -> bytes:
    """ERROR 帧负载：1 字节错误码 + UTF-8 详情。"""
    return bytes([int(code)]) + detail.encode("utf-8")


def parse_error_payload(payload: bytes) -> tuple[int, str]:
    """解析 ERROR 帧负载，返回 (错误码, 详情)。"""
    if not payload:
        return ErrorCode.OK, ""
    return payload[0], payload[1:].decode("utf-8", errors="replace")
