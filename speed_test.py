import os
import time

from src.config import Config
from src.disk import InFileDisk, InMemoryDisk
from src.disks import BaseDisk
from src.path import Directory, FileMode

# ---- HARDCODED TEST SETTINGS ----
FILE_SIZE = 200 * 1024 * 1024  # 200 MB test file
CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB per write/read
DISK_FILENAME = "vdisk_test.bin"  # file for InFileDisk benchmark

# ----------------------------------


def mbps(bytes_amount: int, seconds: float) -> float:
    return (bytes_amount / (1024 * 1024)) / seconds if seconds > 0 else float("inf")


def write_test(root: Directory, filename: bytes, size: int, chunk: int) -> float:
    data = b"\x55" * chunk
    with root.open(
        filename, mode=FileMode.CREATE | FileMode.EXCLUSIVE | FileMode.WRITE
    ) as f:
        remaining = size
        t0 = time.perf_counter()

        while remaining > 0:
            to_write = data if remaining >= chunk else data[:remaining]
            f.write(to_write)
            remaining -= len(to_write)

        f.flush()
        t1 = time.perf_counter()

    return t1 - t0


def read_test(root: Directory, filename: bytes, size: int, chunk: int) -> float:
    with root.open(filename, mode=FileMode.READ) as f:
        remaining = size
        t0 = time.perf_counter()

        while remaining > 0:
            to_read = chunk if remaining >= chunk else remaining
            data = f.read(to_read)
            if not data:
                break
            remaining -= len(data)

        t1 = time.perf_counter()

    return t1 - t0


def run_backend(name: str, disk: BaseDisk):
    print(f"\n===== {name} =====")

    with disk:
        root = disk.root
        filename = b"speed.bin"

        # WRITE
        wtime = write_test(root, filename, FILE_SIZE, CHUNK_SIZE)
        print(
            f"Write: {FILE_SIZE / (1024 * 1024)} MB in {wtime:.3f}s "
            f"-> {mbps(FILE_SIZE, wtime):.2f} MB/s"
        )

        # READ
        rtime = read_test(root, filename, FILE_SIZE, CHUNK_SIZE)
        print(
            f"Read: {FILE_SIZE / (1024 * 1024)} MB in {rtime:.3f}s "
            f"-> {mbps(FILE_SIZE, rtime):.2f} MB/s"
        )


def main(filepath: str):
    cfg = Config(block_size=4096, inode_size=64, num_blocks=65536, num_inodes=65536)

    # ---------- InMemory ----------
    mem_disk = InMemoryDisk(config=cfg)
    run_backend("InMemoryDisk", mem_disk)

    # ---------- InFileDisk ----------
    if os.path.exists(filepath):
        os.remove(filepath)

    file_disk = InFileDisk.new_disk(filepath=filepath, config=cfg)
    run_backend("InFileDisk", file_disk)


if __name__ == "__main__":
    basedir = os.path.dirname(os.path.abspath(__file__))
    instance = os.path.join(basedir, "instance")
    if not os.path.exists(instance):
        os.mkdir(instance)
    filepath = os.path.join(instance, DISK_FILENAME)
    main(filepath)
