from dataclasses import dataclass
from functools import cached_property

from .constants import NUM_DIRECT_PTR
from .utils import ceil_division, floor_division


@dataclass(frozen=True)
class Config:
    block_size: int
    inode_size: int

    num_blocks: int
    num_inodes: int

    @cached_property
    def disk_size(self) -> int:
        return self.block_size * self.num_blocks

    @cached_property
    def block_addr_length(self) -> int:
        return ceil_division(self.num_blocks.bit_length(), 8)

    @cached_property
    def inode_addr_length(self) -> int:
        return ceil_division(self.num_inodes.bit_length(), 8)

    @cached_property
    def num_inode_addr_per_block(self) -> int:
        return floor_division(self.block_size, self.inode_addr_length)

    @cached_property
    def num_inode_addr_double_range(self) -> int:
        return self.num_inode_addr_per_block * self.num_inode_addr_per_block

    @cached_property
    def num_inode_addr_triple_range(self) -> int:
        return self.num_inode_addr_double_range * self.num_inode_addr_per_block

    @cached_property
    def max_file_size(self) -> int:
        return (
            NUM_DIRECT_PTR
            + self.num_inode_addr_per_block
            + self.num_inode_addr_double_range
            + self.num_inode_addr_triple_range
        ) * self.block_size

    @cached_property
    def max_file_size_length(self) -> int:
        return ceil_division(self.max_file_size.bit_length(), 8)

    def __str__(self):
        nl = "\n" + " " * len(self.__class__.__name__)
        return f"""{self.__repr__()[:-1]},{nl} block_addr_length={
            self.block_addr_length
        }, inode_addr_length={self.inode_addr_length},{nl} num_inode_addr_per_block={
            self.num_inode_addr_per_block
        })"""
