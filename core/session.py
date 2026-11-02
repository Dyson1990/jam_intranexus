"""会话控制器：串起发现、连接、消息、文件与存储，供 UI 以协程调用。

所有网络与磁盘操作均为异步或经 ``to_thread``；UI 通过 on_* 钩子（事件循环线程内
触发）接收结果，上层再用 ``Clock.schedule_once`` 转交到 Kivy。设备身份通过
PAIR_REQUEST/PAIR_RESPONSE 握手交换，入站连接据此绑定 peer_id。
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Callable

from plat import default_name, default_save_dir
from storage.db import Database
from .connection import TCP_PORT, Connection, TCPServer, connect
from .discovery import DISCOVERY_PORT, DiscoveryService
from .files import FileReceiver, FileTransfer
from .messages import ChatMessage, MessageStatus, Messenger
from .protocol import Message, MsgType


@dataclass
class PeerLink:
    peer_id: bytes
    name: str
    connection: Connection
    messenger: Messenger
    transfer: FileTransfer


class Session:
    """一台设备的运行时后端；一个进程只应有一个实例。"""

    def __init__(
        self,
        db_path: str,
        tcp_port: int = TCP_PORT,
        discovery_port: int = DISCOVERY_PORT,
        broadcast_interval: float | None = 3.0,
        host: str = "0.0.0.0",
    ) -> None:
        self.db = Database(db_path)
        self.device_id = self._load_device_id()
        self.name = self.db.get_setting("device_name") or default_name()
        self.save_dir = self.db.get_setting("save_dir") or default_save_dir()
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.broadcast_interval = broadcast_interval
        self.host = host

        self.discovery = DiscoveryService(self.device_id, self.name, port=discovery_port, local_addr=host)
        self.server = TCPServer(self.device_id, host=host, port=tcp_port)
        self.server.on_connect = self._on_incoming_conn

        self._links: dict[bytes, PeerLink] = {}
        self._transfers: dict[bytes, dict] = {}
        self._tasks: list[asyncio.Task] = []

        # UI 回调（在事件循环线程内触发）
        self.on_peers_changed: Callable[[], None] | None = None
        self.on_message: Callable[[ChatMessage, bytes], None] | None = None
        self.on_status: Callable[[ChatMessage, bytes], None] | None = None
        self.on_transfer_changed: Callable[[], None] | None = None

    # ---- 生命周期 ----
    async def start(self) -> None:
        await self.discovery.start()
        await self.server.start()
        if self.broadcast_interval is not None:
            self._tasks.append(asyncio.create_task(self._broadcast_loop()))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for link in list(self._links.values()):
            link.connection.close()
        self._links.clear()
        await self.server.stop()
        await self.discovery.stop()
        self.db.close()

    async def _broadcast_loop(self) -> None:
        while True:
            self.discovery.broadcast()
            if self.on_peers_changed is not None:
                self.on_peers_changed()
            await asyncio.sleep(self.broadcast_interval)

    # ---- 身份与设置 ----
    def _load_device_id(self) -> bytes:
        raw = self.db.get_setting("device_id")
        if raw:
            bid = bytes.fromhex(raw)
            if len(bid) == 16:
                return bid
        bid = os.urandom(16)
        self.db.set_setting("device_id", bid.hex())
        return bid

    def set_name(self, name: str) -> None:
        self.name = name
        self.db.set_setting("device_name", name)
        self.discovery.name = name

    def set_save_dir(self, path: str) -> None:
        self.save_dir = path
        self.db.set_setting("save_dir", path)
        for link in self._links.values():
            link.transfer.save_dir = path

    def clear_data(self) -> None:
        """清空本地存储，但保留本机设备 ID（节点身份）。"""
        self.db.clear_all()
        self.db.set_setting("device_id", self.device_id.hex())
        self.name = default_name()
        self.save_dir = default_save_dir()
        self.db.set_setting("device_name", self.name)
        self.db.set_setting("save_dir", self.save_dir)
        self.discovery.name = self.name
        for link in self._links.values():
            link.transfer.save_dir = self.save_dir
        self._transfers.clear()

    # ---- 设备与连接 ----
    def peers(self) -> list[dict]:
        out = []
        for p in self.discovery.online_peers():
            out.append({
                "device_id": p.device_id,
                "name": p.name,
                "address": p.address,
                "connected": p.device_id in self._links,
            })
        return out

    def link_for(self, peer_id: bytes) -> PeerLink | None:
        return self._links.get(peer_id)

    def manual_discover(self, address: str) -> None:
        self.discovery.send_discover_to(address)

    async def connect_peer(self, peer_id: bytes, address: str, name: str = "", tcp_port: int | None = None) -> PeerLink:
        link = self._links.get(peer_id)
        if link is not None and not link.connection.closed:
            return link
        conn = await connect(self.device_id, address, tcp_port or self.tcp_port)
        conn.peer_id = peer_id
        self._attach(conn, peer_id, name)
        await conn.send(MsgType.PAIR_REQUEST, self.name.encode("utf-8"))
        return self._links[peer_id]

    def _on_incoming_conn(self, conn: Connection) -> None:
        conn.router.register(MsgType.PAIR_REQUEST, lambda msg: self._on_pair_request(conn, msg))

    def _on_pair_request(self, conn: Connection, msg: Message) -> None:
        peer_id = msg.sender_id
        name = msg.payload.decode("utf-8", errors="replace")
        conn.peer_id = peer_id
        self._attach(conn, peer_id, name)
        asyncio.get_running_loop().create_task(self._respond_pair(conn))

    async def _respond_pair(self, conn: Connection) -> None:
        try:
            await conn.send(MsgType.PAIR_RESPONSE, self.name.encode("utf-8"))
        except (ConnectionError, OSError):
            pass

    def _attach(self, conn: Connection, peer_id: bytes, name: str) -> PeerLink:
        old = self._links.get(peer_id)
        if old is not None and old.connection is not conn and not old.connection.closed:
            old.connection.close()
        messenger = Messenger(
            conn,
            on_text=lambda m, p=peer_id: self._on_text(p, m),
            on_status=lambda m, p=peer_id: self._on_status(p, m),
        )
        transfer = FileTransfer(conn, save_dir=self.save_dir)
        transfer.on_incoming = lambda r, p=peer_id: self._on_incoming_file(p, r)
        link = PeerLink(peer_id, name or "设备", conn, messenger, transfer)
        self._links[peer_id] = link
        conn.on_close = lambda c=conn, p=peer_id: self._on_link_closed(p, c)
        self.db.upsert_device(peer_id, link.name)
        return link

    def _on_link_closed(self, peer_id: bytes, conn: Connection) -> None:
        link = self._links.get(peer_id)
        if link is not None and link.connection is conn:
            del self._links[peer_id]
        if self.on_peers_changed is not None:
            self.on_peers_changed()

    # ---- 消息 ----
    def message_history(self, peer_id: bytes) -> list[dict]:
        return self.db.list_messages(peer_id)

    async def send_text(self, peer_id: bytes, text: str) -> ChatMessage:
        link = self._links.get(peer_id)
        if link is None or link.connection.closed:
            raise ConnectionError("未连接到该设备")
        msg = await link.messenger.send_text(text)
        self.db.add_message(msg.message_id, peer_id, text, time.time(), "sent", int(MessageStatus.SENT))
        if self.on_message is not None:
            self.on_message(msg, peer_id)
        return msg

    def _on_text(self, peer_id: bytes, msg: ChatMessage) -> None:
        self.db.add_message(msg.message_id, peer_id, msg.text, time.time(), "received", int(MessageStatus.DELIVERED))
        if self.on_message is not None:
            self.on_message(msg, peer_id)

    def _on_status(self, peer_id: bytes, msg: ChatMessage) -> None:
        self.db.update_message_status(msg.message_id, int(msg.status))
        if self.on_status is not None:
            self.on_status(msg, peer_id)

    # ---- 文件 ----
    def active_transfers(self) -> list[dict]:
        return [dict(r) for r in self._transfers.values()]

    async def send_file(self, peer_id: bytes, path: str) -> None:
        link = self._links.get(peer_id)
        if link is None or link.connection.closed:
            raise ConnectionError("未连接到该设备")
        file_id = os.urandom(16)
        name = os.path.basename(path)
        size = os.path.getsize(path)
        self.db.add_transfer(file_id, name, "send", size, peer_id=peer_id, path=path)
        rec = self._new_record(file_id, name, "send", peer_id, size)
        sender = await link.transfer.send_file(
            path, file_id=file_id, on_progress=lambda off, total, f=file_id: self._on_progress(f, off, total)
        )
        if sender.cancelled:
            rec["status"] = "cancelled"
            self.db.update_transfer(file_id, status="cancelled")
        elif sender.finished:
            rec.update(offset=size, status="completed")
            self.db.update_transfer(file_id, offset=size, status="completed")
        else:
            rec["status"] = "failed"
            self.db.update_transfer(file_id, status="failed")
        self._emit_transfer()

    def _on_incoming_file(self, peer_id: bytes, receiver: FileReceiver) -> None:
        file_id = receiver.file_id
        self.db.add_transfer(file_id, receiver.name, "receive", receiver.size, peer_id=peer_id, path=receiver._final_path)
        self._new_record(file_id, receiver.name, "receive", peer_id, receiver.size)
        receiver.on_progress = lambda off, total, f=file_id: self._on_progress(f, off, total)
        receiver.on_done = lambda path, f=file_id: self._on_receive_done(f, path)
        self._emit_transfer()

    def _on_receive_done(self, file_id: bytes, path: str) -> None:
        rec = self._transfers.get(file_id)
        if rec is not None:
            rec["status"] = "completed"
        self.db.update_transfer(file_id, offset=rec["size"] if rec else None, status="completed")
        self._emit_transfer()

    def _new_record(self, file_id: bytes, name: str, direction: str, peer_id: bytes, size: int) -> dict:
        rec = {
            "file_id": file_id, "name": name, "direction": direction, "peer_id": peer_id,
            "size": size, "offset": 0, "status": "active", "speed": 0.0,
            "_off": 0, "_t": time.monotonic(),
        }
        self._transfers[file_id] = rec
        return rec

    def _on_progress(self, file_id: bytes, offset: int, total: int) -> None:
        rec = self._transfers.get(file_id)
        if rec is None:
            return
        now = time.monotonic()
        dt = now - rec["_t"]
        if dt > 0:
            rec["speed"] = (offset - rec["_off"]) / dt
        rec.update(offset=offset, size=total, _off=offset, _t=now)
        self.db.update_transfer(file_id, offset=offset)
        self._emit_transfer()

    def cancel_transfer(self, file_id: bytes) -> None:
        rec = self._transfers.get(file_id)
        if rec is None:
            return
        if rec["direction"] == "send":
            link = self._links.get(rec["peer_id"])
            sender = link.transfer._senders.get(file_id) if link else None
            if sender is not None:
                sender.cancel()
        else:
            for link in self._links.values():
                receiver = link.transfer._receivers.get(file_id)
                if receiver is not None:
                    receiver.cancel()
                    break
        rec["status"] = "cancelled"
        self.db.update_transfer(file_id, status="cancelled")
        self._emit_transfer()

    def _emit_transfer(self) -> None:
        if self.on_transfer_changed is not None:
            self.on_transfer_changed()
