import os

from storage.db import Database


def rand_id() -> bytes:
    return os.urandom(16)


def test_device_upsert_and_list(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        db.upsert_device(rand_id(), "device-a", address="127.0.0.1", port=47900, paired=True)
        db.upsert_device(rand_id(), "device-b")
        assert len(db.list_devices()) == 2
    finally:
        db.close()


def test_device_upsert_is_idempotent(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        did = rand_id()
        db.upsert_device(did, "old-name")
        db.upsert_device(did, "new-name", address="10.0.0.2")
        devices = db.list_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "new-name"
        assert devices[0]["address"] == "10.0.0.2"
    finally:
        db.close()


def test_message_roundtrip(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        peer = rand_id()
        mid = rand_id()
        db.add_message(mid, peer, "hello", 1.0, "sent", 1)
        db.add_message(rand_id(), peer, "hi back", 2.0, "received", 2)
        msgs = db.list_messages(peer)
        assert [m["text"] for m in msgs] == ["hello", "hi back"]
        db.update_message_status(mid, 2)
        assert db.list_messages(peer)[0]["status"] == 2
    finally:
        db.close()


def test_transfer_update(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        fid = rand_id()
        db.add_transfer(fid, "a.bin", "receive", 1000, peer_id=rand_id(), path="/tmp/a.bin")
        db.update_transfer(fid, offset=512)
        t = db.get_transfer(fid)
        assert t["offset"] == 512
        assert t["status"] == "active"
        db.update_transfer(fid, status="completed")
        assert db.get_transfer(fid)["status"] == "completed"
    finally:
        db.close()


def test_settings(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        assert db.get_setting("save_dir") is None
        db.set_setting("save_dir", "C:/downloads")
        assert db.get_setting("save_dir") == "C:/downloads"
    finally:
        db.close()


def test_clear_all(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        db.upsert_device(rand_id(), "d1")
        db.add_message(rand_id(), rand_id(), "hello", 1.0, "sent", 1)
        db.add_transfer(rand_id(), "a.bin", "receive", 100)
        db.set_setting("save_dir", "C:/x")
        db.clear_all()
        assert db.list_devices() == []
        assert db.list_messages(rand_id()) == []
        assert db.list_transfers() == []
        assert db.get_setting("save_dir") is None
    finally:
        db.close()


def test_clear_messages_only(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    try:
        db.upsert_device(rand_id(), "d1")
        db.add_message(rand_id(), rand_id(), "hello", 1.0, "sent", 1)
        db.clear_messages()
        assert db.list_devices()  # 设备记录保留
        assert db.list_messages(rand_id()) == []
    finally:
        db.close()


def test_persistence_across_reopen(tmp_path):
    path = str(tmp_path / "t.db")
    db = Database(path)
    db.upsert_device(rand_id(), "keep-me")
    db.close()
    db2 = Database(path)
    try:
        assert len(db2.list_devices()) == 1
    finally:
        db2.close()
