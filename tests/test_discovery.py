import asyncio
import os

import pytest

from core.discovery import DiscoveryService


def rand_id() -> bytes:
    return os.urandom(16)


async def _drain(delay: float = 0.1):
    await asyncio.sleep(delay)


def test_discover_and_presence_unicast():
    """两台服务在回环地址互发 DISCOVER/PRESENCE，A 应能发现 B。"""
    async def run():
        a = DiscoveryService(rand_id(), "device-a", port=48001, local_addr="127.0.0.1")
        b = DiscoveryService(rand_id(), "device-b", port=48002, local_addr="127.0.0.1")
        await a.start()
        await b.start()
        try:
            a.send_discover_to("127.0.0.1", b.port)
            await _drain()
            peers = a.online_peers()
            assert [p.name for p in peers] == ["device-b"]
            assert peers[0].device_id == b.device_id
            assert peers[0].address == "127.0.0.1"
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(run())


def test_online_timeout():
    async def run():
        a = DiscoveryService(rand_id(), "device-a", port=48003, local_addr="127.0.0.1", timeout=0.05)
        b = DiscoveryService(rand_id(), "device-b", port=48004, local_addr="127.0.0.1")
        await a.start()
        await b.start()
        try:
            a.send_discover_to("127.0.0.1", b.port)
            await _drain(0.02)  # 小于 timeout，仍在在线窗口内
            assert len(a.online_peers()) == 1
            await _drain(0.1)  # 超过 timeout 后应转为离线
            assert a.online_peers() == []
            assert len(a.offline_peers()) == 1
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(run())


def test_ignores_malformed_datagram():
    async def run():
        a = DiscoveryService(rand_id(), "device-a", port=48005, local_addr="127.0.0.1")
        await a.start()
        try:
            a._handle_datagram(b"\x00\x01\x02", ("127.0.0.1", 1))
            assert a.online_peers() == []
        finally:
            await a.stop()

    asyncio.run(run())


def test_device_id_length_guard():
    with pytest.raises(ValueError):
        DiscoveryService(b"short", "x")
