from types import TracebackType
from typing import Self

from ..bitmap import Bitmap
from ..config import Config
from ..inode import Inode, InodeMode
from ..path import Directory
from . import BaseDisk


class InMemoryDisk(BaseDisk):
    def __init__(self, config: Config) -> None:
        self._closed: bool = False

        root_inode = Inode(InodeMode.DIRECTORY)
        if len(root_inode.to_bytes(config)) != config.inode_size:
            raise ValueError(
                f"{config.inode_size=} is too small try={len(root_inode.to_bytes(config))}."
            )

        self.config: Config = config

        self.blocks = [bytearray(config.block_size) for _ in range(config.num_blocks)]

        self.blocks_bitmap: Bitmap = Bitmap(config.num_blocks)

        self.blocks_bitmap.set(
            0
        )  # NOTE/TODO: reserved for super block as also can't have pointer, null_ptr

        self.inodes = [bytearray(config.inode_size) for _ in range(config.num_inodes)]
        self.inodes_bitmap: Bitmap = Bitmap(config.num_inodes)

        self.root = Directory.new(
            disk=self, inode=root_inode, inode_ptr=0, parent_inode_ptr=0
        )
        self.inodes[0][:] = root_inode.to_bytes(config)
        self.inodes_bitmap.set(0)  # NOTE/TODO: for root

    def total_space(self) -> int:
        return self.config.disk_size

    def free_space(self) -> int:
        return self.config.block_size * self.blocks_bitmap.free_count()

    def used_space(self) -> int:
        return self.total_space() - self.free_space()

    def reserved_space(self) -> int:
        return self.config.block_size  # NOTE: we are storing inodes separately.

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> Self:
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
