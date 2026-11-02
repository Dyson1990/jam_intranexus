import asyncio
import os

from core.connection import TCPServer, connect
from core.files import (
    CHUNK_SIZE,
    FileReceiver,
    FileTransfer,
    decode_offer,
    encode_chunk,
    encode_offer,
)
from core.protocol import Message, MsgType


def rand_id() -> bytes:
    return os.urandom(16)


async def wait_until(predicate, timeout: float = 5.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


def _make_file(tmp_path, nbytes: int) -> tuple[str, bytes]:
    data = os.urandom(nbytes)
    p = tmp_path / "in.bin"
    p.write_bytes(data)
    return str(p), data


def test_offer_codec_roundtrip():
    fid = os.urandom(16)
    sha = os.urandom(32)
    fid2, name, size, sha2 = decode_offer(encode_offer(fid, "测试.txt", 123, sha))
    assert fid2 == fid
    assert name == "测试.txt"
    assert size == 123
    assert sha2 == sha


def test_full_transfer(tmp_path):
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48300)
        await server.start()
        try:
            conn = await connect(rand_id(), "127.0.0.1", 48300, heartbeat_interval=None)
            await wait_until(lambda: len(server.connections) == 1)
            rconn = next(iter(server.connections))

            save_dir = tmp_path / "recv"
            src, data = _make_file(tmp_path, 300_000)

            FileTransfer(rconn, save_dir=str(save_dir))
            sft = FileTransfer(conn)
            await sft.send_file(src)

            final = save_dir / "in.bin"
            await wait_until(lambda: final.exists())
            assert final.read_bytes() == data
        finally:
            await server.stop()

    asyncio.run(run())


def test_resume_from_partial(tmp_path):
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48301)
        await server.start()
        try:
            conn = await connect(rand_id(), "127.0.0.1", 48301, heartbeat_interval=None)
            await wait_until(lambda: len(server.connections) == 1)
            rconn = next(iter(server.connections))

            save_dir = tmp_path / "recv"
            src, data = _make_file(tmp_path, 300_000)
            half = len(data) // 2
            save_dir.mkdir()
            (save_dir / "in.bin.part").write_bytes(data[:half])  # 预置半份，模拟断点

            FileTransfer(rconn, save_dir=str(save_dir))
            sft = FileTransfer(conn)
            await sft.send_file(src)

            final = save_dir / "in.bin"
            await wait_until(lambda: final.exists())
            assert final.read_bytes() == data
        finally:
            await server.stop()

    asyncio.run(run())


def test_sender_cancel(tmp_path):
    async def run():
        server = TCPServer(rand_id(), host="127.0.0.1", port=48302)
        await server.start()
        try:
            conn = await connect(rand_id(), "127.0.0.1", 48302, heartbeat_interval=None)
            await wait_until(lambda: len(server.connections) == 1)
            rconn = next(iter(server.connections))

            save_dir = tmp_path / "recv"
            src, _ = _make_file(tmp_path, 5_000_000)

            FileTransfer(rconn, save_dir=str(save_dir))
            sft = FileTransfer(conn)

            holder: dict = {}

            def on_progress(sent, total):
                if sent >= CHUNK_SIZE and "s" in holder and not holder["s"].cancelled:
                    holder["s"].cancel()

            task = asyncio.create_task(sft.send_file(src, on_progress=on_progress))
            await wait_until(lambda: bool(sft._senders))
            holder["s"] = next(iter(sft._senders.values()))
            await task

            assert not (save_dir / "in.bin").exists()
        finally:
            await server.stop()

    asyncio.run(run())


def test_receiver_checksum_mismatch(tmp_path):
    async def run():
        save_dir = tmp_path / "recv"
        file_id = os.urandom(16)
        data = os.urandom(1000)
        receiver = FileReceiver(
            None, str(save_dir), file_id, "f.bin", len(data), b"\x00" * 32
        )
        receiver._handle_chunk(Message(rand_id(), MsgType.FILE_CHUNK, encode_chunk(file_id, 0, data)))
        receiver._completed = True
        receiver._queue.put_nowait(None)
        await receiver.run()
        assert not (save_dir / "f.bin").exists()
        assert (save_dir / "f.bin.part").exists()

    asyncio.run(run())
