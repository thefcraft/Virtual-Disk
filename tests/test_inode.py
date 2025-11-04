from . import config
from src.inode import Inode, InodeMode

def test_encode_decode():
    inode = Inode(InodeMode.DIRECTORY)
    assert Inode.from_bytes(inode.to_bytes(config), config) == inode
    