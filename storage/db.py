"""SQLite 存储层：设备 / 消息 / 传输任务 / 设置。

同步接口，供上层（UI 经 Clock、网络经 to_thread）调用；与网络、UI 解耦。
二进制 ID（设备/消息/文件）以十六进制文本存库，便于查询与调试。
"""
from __future__ import annotations

import sqlite3
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    port INTEGER,
    paired INTEGER NOT NULL DEFAULT 0,
    last_seen REAL
);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    peer_id TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp REAL NOT NULL,
    direction TEXT NOT NULL,
    status INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_peer ON messages(peer_id, timestamp);
CREATE TABLE IF NOT EXISTS transfers (
    file_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    direction TEXT NOT NULL,
    peer_id TEXT,
    size INTEGER NOT NULL,
    offset INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    path TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _hex(b: bytes) -> str:
    return b.hex()


class Database:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---- 设备 ----
    def upsert_device(self, device_id: bytes, name: str, address: str | None = None,
                      port: int | None = None, paired: bool = False,
                      last_seen: float | None = None) -> None:
        self._conn.execute(
            "INSERT INTO devices(device_id, name, address, port, paired, last_seen) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "name=excluded.name, address=excluded.address, port=excluded.port, "
            "paired=excluded.paired, last_seen=excluded.last_seen",
            (_hex(device_id), name, address, port, int(paired), last_seen),
        )
        self._conn.commit()

    def list_devices(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_device(self, device_id: bytes) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM devices WHERE device_id = ?", (_hex(device_id),)
        ).fetchone()
        return dict(row) if row else None

    # ---- 消息 ----
    def add_message(self, message_id: bytes, peer_id: bytes, text: str,
                    timestamp: float, direction: str, status: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO messages(message_id, peer_id, text, timestamp, direction, status) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (_hex(message_id), _hex(peer_id), text, timestamp, direction, status),
        )
        self._conn.commit()

    def list_messages(self, peer_id: bytes, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE peer_id = ? ORDER BY timestamp ASC LIMIT ?",
            (_hex(peer_id), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_message_status(self, message_id: bytes, status: int) -> None:
        self._conn.execute(
            "UPDATE messages SET status = ? WHERE message_id = ?", (status, _hex(message_id))
        )
        self._conn.commit()

    # ---- 传输任务 ----
    def add_transfer(self, file_id: bytes, name: str, direction: str, size: int,
                     peer_id: bytes | None = None, path: str | None = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO transfers(file_id, name, direction, peer_id, size, offset, status, path) "
            "VALUES(?, ?, ?, ?, ?, 0, 'active', ?)",
            (_hex(file_id), name, direction, _hex(peer_id) if peer_id else None, size, path),
        )
        self._conn.commit()

    def update_transfer(self, file_id: bytes, offset: int | None = None,
                        status: str | None = None) -> None:
        sets: list[str] = []
        args: list[Any] = []
        if offset is not None:
            sets.append("offset = ?")
            args.append(offset)
        if status is not None:
            sets.append("status = ?")
            args.append(status)
        if not sets:
            return
        args.append(_hex(file_id))
        self._conn.execute(f"UPDATE transfers SET {', '.join(sets)} WHERE file_id = ?", args)
        self._conn.commit()

    def get_transfer(self, file_id: bytes) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM transfers WHERE file_id = ?", (_hex(file_id),)
        ).fetchone()
        return dict(row) if row else None

    def list_transfers(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM transfers ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ---- 设置 ----
    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value)
        )
        self._conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
