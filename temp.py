import os

from src.virtual_disk.config import Config
from src.virtual_disk.disk import InFileChaCha20EncryptedDisk, InFileDisk, InMemoryDisk
from src.virtual_disk.disks import BaseDisk
from src.virtual_disk.path import Directory, FileMode

DISK_FILENAME = "vdisk_temp.bin"


def run_backend(name: str, disk: BaseDisk):
    print(f"\n===== {name} =====")

    with disk:
        filename = b"readme.md"
        with disk.root.open(name=filename, mode="wb") as f:
            f.write(b"why encryption is important...")


def main(filepath: str):
    cfg = Config(block_size=4096, inode_size=64, num_blocks=16, num_inodes=16)

    # ---------- InFileDisk ----------
    if os.path.exists(filepath):
        os.remove(filepath)

    # file_disk = InFileDisk.new_disk(filepath=filepath, config=cfg)
    file_disk = InFileChaCha20EncryptedDisk.new_disk(
        filepath=filepath, config=cfg, password=b"password"
    )
    run_backend("InFileDisk", file_disk)


if __name__ == "__main__":
    basedir = os.path.dirname(os.path.abspath(__file__))
    instance = os.path.join(basedir, "instance")
    if not os.path.exists(instance):
        os.mkdir(instance)
    filepath = os.path.join(instance, DISK_FILENAME)
    main(filepath)
