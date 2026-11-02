"""UDP 广播设备发现：DISCOVER/PRESENCE 交换，维护对端在线状态。

PRESENCE 负载为设备名（UTF-8）；设备 ID 取自协议头 sender_id，对端 IP/端口取自
UDP 数据报源地址。在线判定基于 last_seen 超时，不主动探测，由上层周期广播触发。
"""
from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass, field

from .protocol import DEVICE_ID_SIZE, Message, MsgType, ProtocolError

DISCOVERY_PORT = 47899
BROADCAST_ADDR = "255.255.255.255"


@dataclass
class Peer:
    device_id: bytes
    name: str
    address: str
    port: int
    last_seen: float = field(default_factory=time.monotonic)


def get_local_ips() -> list[str]:
    """枚举本机 IPv4 地址（供手动 IP 连接与界面展示）。"""
    ips: list[str] = []
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


class DiscoveryService:
    """一台设备的发现服务：监听 UDP 端口，响应 DISCOVER 并记录 PRESENCE。"""

    def __init__(
        self,
        device_id: bytes,
        name: str,
        port: int = DISCOVERY_PORT,
        timeout: float = 30.0,
        local_addr: str = "0.0.0.0",
    ) -> None:
        if len(device_id) != DEVICE_ID_SIZE:
            raise ValueError(f"device_id must be {DEVICE_ID_SIZE} bytes")
        self.device_id = device_id
        self.name = name
        self.port = port
        self.timeout = timeout
        self.local_addr = local_addr
        self._transport: asyncio.DatagramTransport | None = None
        self._peers: dict[bytes, Peer] = {}
        self._on_peer_update: asyncio.Task | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self),
            local_addr=(self.local_addr, self.port),
            allow_broadcast=True,
        )

    async def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def broadcast(self) -> None:
        """向广播地址发送 DISCOVER；限内网，收到方各自回 PRESENCE。"""
        self._send(MsgType.DISCOVER, BROADCAST_ADDR, self.port)

    def send_discover_to(self, address: str, port: int | None = None) -> None:
        """手动 IP 连接：向指定地址单播 DISCOVER。"""
        self._send(MsgType.DISCOVER, address, port or self.port)

    def _send(self, msg_type: int, address: str, port: int) -> None:
        if self._transport is None:
            raise RuntimeError("DiscoveryService not started")
        frame = Message(sender_id=self.device_id, msg_type=msg_type).encode()
        self._transport.sendto(frame, (address, port))

    def online_peers(self) -> list[Peer]:
        """返回未超时的对端列表，并按 last_seen 排序。"""
        now = time.monotonic()
        peers = [p for p in self._peers.values() if now - p.last_seen <= self.timeout]
        return sorted(peers, key=lambda p: p.last_seen)

    def offline_peers(self) -> list[Peer]:
        now = time.monotonic()
        return [p for p in self._peers.values() if now - p.last_seen > self.timeout]

    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = Message.decode(data)
        except ProtocolError:
            return  # 忽略无法解析的包
        if msg.msg_type == MsgType.DISCOVER:
            self._respond_presence(addr)
        elif msg.msg_type == MsgType.PRESENCE:
            self._record_presence(msg, addr)

    def _respond_presence(self, addr: tuple[str, int]) -> None:
        if self._transport is None:
            return
        frame = Message(
            sender_id=self.device_id,
            msg_type=MsgType.PRESENCE,
            payload=self.name.encode("utf-8"),
        ).encode()
        self._transport.sendto(frame, addr)

    def _record_presence(self, msg: Message, addr: tuple[str, int]) -> None:
        if msg.sender_id == self.device_id:
            return  # 忽略自身广播回环
        self._peers[msg.sender_id] = Peer(
            device_id=msg.sender_id,
            name=msg.payload.decode("utf-8", errors="replace"),
            address=addr[0],
            port=addr[1],
        )


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, service: DiscoveryService) -> None:
        self.service = service

    def datagram_received(self, data: bytes, addr) -> None:
        self.service._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        # UDP 无连接，个别包错误不影响服务；记录即可，避免崩溃
        pass
