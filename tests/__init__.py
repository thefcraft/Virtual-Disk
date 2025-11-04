from src.disk import InMemoryDisk
from src.config import Config


from functools import wraps
from typing import Callable, TypeVar, ParamSpec

config = Config(
    block_size=4096,
    inode_size=64,
    num_blocks=1024*128,
    num_inodes=1024
)

disk = InMemoryDisk(
    config=config
)

P = ParamSpec("P")
R = TypeVar("R")

def assert_disk_not_changed(func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to assert that disk state remains unchanged
    across the wrapped test function.
    
    Usage:
        @assert_disk_not_changed
        def test_something(disk, ...):
            ...
    """
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        root = disk.root
        root_before = root.inode_io.read_at(0)
        super_block = disk.blocks[0]
        super_inode = disk.inodes[0]
        free_block_before = disk.blocks_bitmap.free_count()
        free_inode_before = disk.inodes_bitmap.free_count()
        
        result = func(*args, **kwargs)

        assert disk.blocks_bitmap.free_count() == free_block_before, "Block bitmap changed"
        assert disk.inodes_bitmap.free_count() == free_inode_before, "Inode bitmap changed"
        assert root.inode_io.read_at(0) == root_before, "Root inode content changed"
        assert disk.blocks[0] == super_block, "Superblock changed"
        assert disk.inodes[0] == super_inode, "Super inode changed"

        return result

    return wrapper
