from ..config import Config
from ..bitmap import Bitmap
from ..inode import Inode, InodeMode
from ..path import Directory

from .. import protocol

class InMemoryDisk(protocol.Disk):
    def __init__(self, config: Config) -> None:
        root_inode = Inode(InodeMode.DIRECTORY)
        if len(root_inode.to_bytes(config)) != config.inode_size:
            raise ValueError(f"{config.inode_size=} is too small try={len(root_inode.to_bytes(config))}.")
        
        self.config: Config = config
        
        self.blocks = [
            bytearray(config.block_size)
            for _ in range(config.num_blocks)
        ]
        self.blocks_bitmap: Bitmap = Bitmap(config.num_blocks)
        
        self.blocks_bitmap.set(0) # NOTE/TODO: reserved for super block as also can't have pointer, null_ptr
        
        self.inodes = [
            bytearray(config.inode_size)
            for _ in range(config.num_inodes)
        ]
        self.inodes_bitmap: Bitmap = Bitmap(config.num_inodes)
        
        self.root = Directory.new(
            disk=self,
            inode=root_inode, 
            inode_ptr=0,
            parent_inode_ptr=0
        )
        self.inodes[0][:] = root_inode.to_bytes(config)
        self.inodes_bitmap.set(0) # NOTE/TODO: for root