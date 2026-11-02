"""标准库实现的对称认证加密：HMAC-SHA256 计数器模式流加密 + 加密后 MAC。

仅依赖 hashlib/hmac/os，避免在 Android 上编译 C 扩展（cryptography / pycryptodome 均
需 recipe，是本项目 4.4 的阻塞点）。每帧随机 12 字节 nonce，密钥流由
HMAC-SHA256(key, nonce || counter) 生成，密文后附 16 字节 HMAC-SHA256 标签
（encrypt-then-MAC）。仅用于抵御同网段被动嗅探，不替代 TLS 等完整传输安全。

帧格式: nonce(12) || ciphertext || tag(16)
"""
from __future__ import annotations

import hashlib
import hmac
import os

NONCE_SIZE = 12
TAG_SIZE = 16
_COUNTER_SIZE = 8
_BLOCK_SIZE = 32  # SHA-256 摘要长度


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    """HMAC-SHA256 计数器模式密钥流，截断到目标长度。"""
    parts = bytearray()
    for counter in range((length + _BLOCK_SIZE - 1) // _BLOCK_SIZE):
        parts += hmac.new(enc_key, nonce + counter.to_bytes(_COUNTER_SIZE, "big"),
                          hashlib.sha256).digest()
    return bytes(parts[:length])


def _xor(a: bytes, b: bytes) -> bytes:
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")


def derive_keys(pair_key: str) -> tuple[bytes, bytes]:
    """由用户配对密钥派生加密/认证两把子密钥（域分离 HMAC 简化版 HKDF）。"""
    material = hashlib.sha256(pair_key.encode("utf-8")).digest()
    enc = hmac.new(material, b"jam_intranexus/enc", hashlib.sha256).digest()
    mac = hmac.new(material, b"jam_intranexus/mac", hashlib.sha256).digest()
    return enc, mac


class FrameCipher:
    """把「整帧明文」加/解密为「nonce+密文+标签」的自包含块。"""

    def __init__(self, pair_key: str) -> None:
        self.enc_key, self.mac_key = derive_keys(pair_key)

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = _xor(plaintext, _keystream(self.enc_key, nonce, len(plaintext)))
        tag = hmac.new(self.mac_key, nonce + ciphertext, hashlib.sha256).digest()[:TAG_SIZE]
        return nonce + ciphertext + tag

    def decrypt(self, frame: bytes) -> bytes:
        if len(frame) < NONCE_SIZE + TAG_SIZE:
            raise ValueError("frame too short")
        nonce = frame[:NONCE_SIZE]
        tag = frame[-TAG_SIZE:]
        ciphertext = frame[NONCE_SIZE:-TAG_SIZE]
        expected = hmac.new(self.mac_key, nonce + ciphertext, hashlib.sha256).digest()[:TAG_SIZE]
        if not hmac.compare_digest(tag, expected):
            raise ValueError("authentication failed")
        return _xor(ciphertext, _keystream(self.enc_key, nonce, len(ciphertext)))
