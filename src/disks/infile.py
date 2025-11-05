from ..config import Config
from ..bitmap import Bitmap
from ..inode import Inode, InodeMode
from ..path import Directory
from ..utils import ceil_division
from ..constants import NULL_BYTES

from .. import protocol
from .import BaseDisk

import os

from typing import Iterator, Self, BinaryIO
from types import TracebackType

from enum import IntEnum, auto

SUPER_BLOCK_DATA_LENGTH = 12

class InFileDiskType(IntEnum):
    NON_ENCRYPTED = 0
    CHA_CHA_20_ENCRYPTED = 1


def load_config_from_file(file: BinaryIO) -> Config:
    block_size = int.from_bytes(
        file.read(SUPER_BLOCK_DATA_LENGTH),
        byteorder='big', signed=False
    )
    inode_size = int.from_bytes(
        file.read(SUPER_BLOCK_DATA_LENGTH),
        byteorder='big', signed=False
    )
    num_blocks = int.from_bytes(
        file.read(SUPER_BLOCK_DATA_LENGTH),
        byteorder='big', signed=False
    )
    num_inodes = int.from_bytes(
        file.read(SUPER_BLOCK_DATA_LENGTH),
        byteorder='big', signed=False
    )
    if block_size < file.tell():
        raise RuntimeError(f"{block_size=} is smaller then {file.tell()=}, matbe disk is corrupted.")
    return Config(
        block_size=block_size,
        inode_size=inode_size,
        num_blocks=num_blocks,
        num_inodes=num_inodes
    )    
    
def dump_config(config: Config) -> bytes: 
    header = config.block_size.to_bytes(
        length=SUPER_BLOCK_DATA_LENGTH, byteorder='big', signed=False
    ) + config.inode_size.to_bytes(
        length=SUPER_BLOCK_DATA_LENGTH, byteorder='big', signed=False
    ) + config.num_blocks.to_bytes(
        length=SUPER_BLOCK_DATA_LENGTH, byteorder='big', signed=False
    ) + config.num_inodes.to_bytes(
        length=SUPER_BLOCK_DATA_LENGTH, byteorder='big', signed=False
    )
    if config.block_size < len(header):
        raise RuntimeError(f"{config.block_size=} is too small try {len(header)=}.")
    return header


def dump_bitmap(bitmap: Bitmap) -> bytes: 
    return bytes(bitmap._data)

class BitmapFile(Bitmap):
    def __init__(self, size: int, file: BinaryIO, *, pos: int):
        self._size: int = size
        self.file: BinaryIO = file
        self.pos: int = pos
        
        self.size_bytes: int = ceil_division(size, 8)
        self.file.seek(self.pos, os.SEEK_SET)
        self._data: bytearray = bytearray(file.read(self.size_bytes))
        if len(self._data) != self.size_bytes:
            raise RuntimeError(f"file is too small, unable to read {self.size_bytes=} content, matbe disk is corrupted.")

    def set(self, index: int): 
        if not (0 <= index < self._size): raise IndexError("Bitmap index out of range")
        idx: int = index // 8
        self._data[idx] |= 1 << (index % 8)
        self.file.seek(self.pos + idx, os.SEEK_SET)
        self.file.write(self._data[idx:idx+1])
        
    def clear(self, index: int):
        if not (0 <= index < self._size): raise IndexError("Bitmap index out of range")
        idx: int = index // 8
        self._data[idx] &= ~(1 << (index % 8))
        self.file.seek(self.pos + idx, os.SEEK_SET)
        self.file.write(self._data[idx:idx+1])

class InodeView(protocol.InodeView):
    def __init__(self, file: BinaryIO, data: bytes, pos: int) -> None:
        self.file: BinaryIO = file
        self.pos: int = pos
        self.data: bytearray = bytearray(data)
        self.inode_size: int = len(data)
    def __repr__(self) -> str:
        return self.data.__repr__()
    def __len__(self) -> int: return self.inode_size
    def __setitem__(
        self, 
        idx: "slice[None, None, None]", 
        value: bytes, /
    ):
        self.data[idx] = value
        self.file.seek(self.pos, os.SEEK_SET)
        self.file.write(value)
    def __getitem__(
        self,
        idx: "slice[int, int, None]", /
    ) -> bytes:
        return self.data[idx]
 
class InodesList(protocol.InodesList): 
    def __init__(self, file: BinaryIO, *, pos: int, inode_size: int, num_inodes: int) -> None:
        self.file: BinaryIO = file
        self.pos: int = pos
        self.inode_size: int = inode_size
        self.num_inodes: int = num_inodes
        
    def __getitem__(self, idx: int, /) -> InodeView: 
        if idx >= self.num_inodes or idx < 0: 
            raise IndexError(f"{idx=} out of range.")
        pos = self.pos + idx * self.inode_size
        self.file.seek(pos, os.SEEK_SET)
        data: bytes = self.file.read(self.inode_size)
        if len(data) != self.inode_size:
            raise RuntimeError(f"read {len(data)=} but expeted {self.inode_size=}.")
        return InodeView(
            self.file,
            data=data,
            pos=pos
        )

class BlockView(protocol.BlockView):
    def __init__(self, file: BinaryIO, data: bytes, pos: int) -> None:
        self.file: BinaryIO = file
        self.pos: int = pos
        self.data: bytearray = bytearray(data)
    def __repr__(self) -> str:
        return self.data.__repr__()
    def __setitem__(
        self, 
        idx: "slice[int | None, int | None, None]", 
        value: bytes, /
    ):
        self.data[idx] = value
        pos = self.pos + (
            0 if idx.start is None else idx.start
        )
        self.file.seek(pos, os.SEEK_SET)
        self.file.write(value)
        
    def __iter__(self) -> Iterator[int]: 
        yield from self.data
    def __getitem__(
        self,
        idx: "slice[int | None, int | None, None]", /
    ) -> bytes:
        return self.data[idx]
   
class BlocksList(protocol.BlocksList): 
    def __init__(self, file: BinaryIO, *, block_size: int, num_blocks: int) -> None:
        self.file: BinaryIO = file
        self.block_size: int = block_size
        self.num_blocks: int = num_blocks
    def __getitem__(self, idx: int, /) -> BlockView: 
        if idx >= self.num_blocks or idx < 0: 
            raise IndexError(f"{idx=} out of range.")
        pos = idx * self.block_size
        self.file.seek(pos, os.SEEK_SET)
        data: bytes = self.file.read(self.block_size)
        if len(data) != self.block_size:
            raise RuntimeError(f"read {len(data)=} but expeted {self.block_size=}.")
        return BlockView(
            self.file,
            data=data,
            pos=pos
        )
        
        
class InFileDisk(BaseDisk):
    root: Directory
    file: BinaryIO
    _reserved_space: int
    
    def __init__(self, filepath: str | BinaryIO) -> None:
        if isinstance(filepath, str):
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"{filepath=} not exists.")    
            self.file = open(filepath, "rb+")
        else:
            self.file = filepath
        self._closed: bool = False
        
        try:
            disk_type = InFileDiskType(int.from_bytes(
                self.file.read(1), byteorder='big', signed=False
            ))
        except ValueError:
            raise TypeError(
                f"{filepath=} is not of {self.__class__.__name__} type."
                f" maybe disk is corrupted."
            )
        if disk_type != InFileDiskType.NON_ENCRYPTED:
            raise TypeError(
                f"{filepath=} is not of {self.__class__.__name__} type."
                f" Please use approprate disk class to load it."
                f" {disk_type=};"
            )
            
        self.config = load_config_from_file(self.file)
        
        len_config_bytes: int = self.file.tell()
        
        self.inodes_bitmap = BitmapFile(self.config.num_inodes, self.file, 
                                        pos=len_config_bytes)
        self.blocks_bitmap = BitmapFile(self.config.num_blocks, self.file, 
                                        pos=len_config_bytes + self.inodes_bitmap.size_bytes)
        
        header_prefix_size_required: int = (
            len_config_bytes + 
            self.inodes_bitmap.size_bytes +
            self.blocks_bitmap.size_bytes
        )
        header_size_required: int = (
            header_prefix_size_required + 
            self.config.inode_size * self.config.num_inodes
        )
        self._reserved_space = header_size_required
        
        disk_size = self.config.disk_size
        if disk_size < (header_size_required + self.config.block_size):
            raise ValueError(
                f"{disk_size=} is too small try {header_size_required + self.config.block_size}, matbe disk is corrupted."
            )
        num_super_blocks: int = ceil_division(header_size_required, self.config.block_size)
        if num_super_blocks == 0:
            raise RuntimeError(f"Something went wrong, {num_super_blocks=} should not be zero, matbe disk is corrupted.")
        for i in range(num_super_blocks):
            if not self.blocks_bitmap.get(i):
                raise RuntimeError(f"Something went wrong, {self.blocks_bitmap.get(i)=}[{i=}] should be set, matbe disk is corrupted.")        
        
        if not self.inodes_bitmap.get(0):
            raise RuntimeError(f"Something went wrong, {self.inodes_bitmap.get(0)=} should be set, matbe disk is corrupted.")        
        
        self.inodes = InodesList(
            self.file, 
            pos=header_prefix_size_required,
            inode_size=self.config.inode_size, 
            num_inodes=self.config.num_inodes
        )
        self.blocks = BlocksList(
            self.file, 
            block_size=self.config.block_size, 
            num_blocks=self.config.num_blocks
        )
        
        root_inode = Inode.from_bytes(
            data=self.inodes[0],
            config=self.config
        )
        self.root = Directory(
            disk=self,
            inode=root_inode, 
            inode_ptr=0
        )
        
    @classmethod
    def new_disk(cls, filepath: str | BinaryIO, config: Config) -> Self:
        disk_size = config.disk_size
        
        self = cls.__new__(cls)
        
        root_inode = Inode(InodeMode.DIRECTORY)
        if len(root_inode.to_bytes(config)) != config.inode_size:
            raise ValueError(f"{config.inode_size=} is too small try={len(root_inode.to_bytes(config))}.")
        
        self.config = config
        config_bytes: bytes = dump_config(config)
        
        if isinstance(filepath, str):
            if os.path.exists(filepath):
                raise FileExistsError(f"{filepath=} already exists.")
            self.file = open(filepath, "wb+")
        else:
            self.file = filepath
        self._closed = False
        self.file.write(InFileDiskType.NON_ENCRYPTED.value.to_bytes(
            length=1, byteorder='big', signed=False
        )) # NOTE: first byte should be NULL_BYTES/NON_ENCRYPTED=0 for class InFileDisk 
        self.file.write(config_bytes)
        len_config_bytes: int = self.file.tell()
        
        self.file.seek(disk_size - 1, os.SEEK_SET)
        self.file.write(NULL_BYTES) # NOTE: created file with config...
        
        
        self.inodes_bitmap = BitmapFile(config.num_inodes, self.file, 
                                        pos=len_config_bytes)
        self.blocks_bitmap = BitmapFile(config.num_blocks, self.file, 
                                        pos=len_config_bytes + self.inodes_bitmap.size_bytes)
        
        
        header_prefix_size_required: int = (
            len_config_bytes + 
            self.inodes_bitmap.size_bytes +
            self.blocks_bitmap.size_bytes
        )
        header_size_required: int = (
            header_prefix_size_required + 
            config.inode_size * config.num_inodes
        )
        self._reserved_space = header_size_required
        
        if disk_size < (header_size_required + self.config.block_size):
            raise ValueError(
                f"{disk_size=} is too small try {header_size_required + self.config.block_size}."
            )
            
        num_super_blocks: int = ceil_division(header_size_required, config.block_size)
        if num_super_blocks == 0:
            raise RuntimeError(f"Something went wrong, {num_super_blocks=} should not be zero.")
        for i in range(num_super_blocks):
            self.blocks_bitmap.set(i) # for super blocks
        
        self.inodes = InodesList(
            self.file, 
            pos=header_prefix_size_required,
            inode_size=self.config.inode_size, 
            num_inodes=self.config.num_inodes
        )
        self.blocks = BlocksList(
            self.file, 
            block_size=self.config.block_size, 
            num_blocks=self.config.num_blocks
        )
        
        self.root = Directory.new(
            disk=self,
            inode=root_inode, 
            inode_ptr=0,
            parent_inode_ptr=0
        )
        
        self.inodes[0][:] = root_inode.to_bytes(config)
        self.inodes_bitmap.set(0) # for root
        
        return self
    
    def total_space(self) -> int: 
        return self.config.disk_size
    def free_space(self) -> int: 
        return self.config.block_size * self.blocks_bitmap.free_count()
    def used_space(self) -> int: 
        return self.total_space() - self.free_space()
    def reserved_space(self) -> int: 
        return self._reserved_space
    
    @property
    def closed(self) -> bool: 
        return self._closed
    def close(self) -> None: 
        if self._closed: return None
        self._closed = True
        self.file.close()
    def __enter__(self) -> Self: 
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self
    def __exit__(self, 
                 exc_type: type[BaseException] | None, 
                 exc_val: BaseException | None, 
                 exc_tb: TracebackType | None) -> None: self.close()
