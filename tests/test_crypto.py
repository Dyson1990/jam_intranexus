"""标准库对称加密：加解密往返、篡改检测、密钥隔离。"""
import os

import pytest

from core.crypto import FrameCipher, derive_keys


def test_roundtrip():
    c = FrameCipher("secret")
    for data in (b"", b"x", os.urandom(1000), os.urandom(100_000)):
        assert c.decrypt(c.encrypt(data)) == data


def test_tamper_detected():
    c = FrameCipher("secret")
    frame = bytearray(c.encrypt(b"hello world"))
    frame[len(frame) // 2] ^= 0x01
    with pytest.raises(ValueError):
        c.decrypt(bytes(frame))


def test_wrong_key_rejected():
    a = FrameCipher("aaa")
    b = FrameCipher("bbb")
    with pytest.raises(ValueError):
        b.decrypt(a.encrypt(b"payload"))


def test_derive_distinct_keys():
    enc, mac = derive_keys("secret")
    assert enc != mac
    assert len(enc) == 32 and len(mac) == 32
