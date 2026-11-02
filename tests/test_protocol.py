import os
import struct

import pytest

from core.protocol import (
    DEVICE_ID_SIZE,
    HEADER_FMT,
    HEADER_SIZE,
    MAGIC,
    MAX_PAYLOAD,
    VERSION,
    ErrorCode,
    Message,
    MsgType,
    ProtocolError,
    build_error_payload,
    parse_error_payload,
)


def rand_id() -> bytes:
    return os.urandom(DEVICE_ID_SIZE)


def test_roundtrip():
    payload = os.urandom(1024)
    m = Message(sender_id=rand_id(), msg_type=MsgType.TEXT, payload=payload)
    assert Message.decode(m.encode()) == m


def test_empty_payload_roundtrip():
    m = Message(sender_id=rand_id(), msg_type=MsgType.DISCOVER)
    assert Message.decode(m.encode()) == m


def test_bad_magic():
    m = Message(sender_id=rand_id(), msg_type=MsgType.TEXT)
    raw = bytearray(m.encode())
    raw[:4] = b"XXXX"
    with pytest.raises(ProtocolError) as e:
        Message.decode(bytes(raw))
    assert e.value.code == ErrorCode.BAD_HEADER


def test_bad_version():
    m = Message(sender_id=rand_id(), msg_type=MsgType.TEXT)
    raw = bytearray(m.encode())
    raw[4] = VERSION + 1
    with pytest.raises(ProtocolError) as e:
        Message.decode(bytes(raw))
    assert e.value.code == ErrorCode.BAD_HEADER


def test_truncated_frame():
    m = Message(sender_id=rand_id(), msg_type=MsgType.TEXT, payload=b"hello")
    with pytest.raises(ProtocolError) as e:
        Message.decode(m.encode()[:-1])
    assert e.value.code == ErrorCode.INVALID_LENGTH


def test_short_header():
    with pytest.raises(ProtocolError) as e:
        Message.decode(b"\x00" * (HEADER_SIZE - 1))
    assert e.value.code == ErrorCode.INVALID_LENGTH


def test_oversize_payload_len_field():
    """头部声明超限长度时应在读取负载前拒绝。"""
    header = struct.pack(HEADER_FMT, MAGIC, VERSION, MsgType.TEXT, 0, rand_id(), MAX_PAYLOAD + 1)
    with pytest.raises(ProtocolError) as e:
        Message.decode(header)
    assert e.value.code == ErrorCode.INVALID_LENGTH


def test_encode_rejects_oversize_payload():
    with pytest.raises(ProtocolError):
        Message(sender_id=rand_id(), msg_type=MsgType.TEXT, payload=b"\x00" * (MAX_PAYLOAD + 1))


def test_encode_rejects_bad_device_id():
    with pytest.raises(ProtocolError):
        Message(sender_id=b"short", msg_type=MsgType.TEXT)


def test_error_payload_roundtrip():
    payload = build_error_payload(ErrorCode.CHECKSUM_MISMATCH, "sha mismatch")
    code, detail = parse_error_payload(payload)
    assert code == ErrorCode.CHECKSUM_MISMATCH
    assert detail == "sha mismatch"


def test_error_payload_empty_detail():
    code, detail = parse_error_payload(build_error_payload(ErrorCode.OK))
    assert code == ErrorCode.OK
    assert detail == ""


def test_header_size_stable():
    assert HEADER_SIZE == 27
