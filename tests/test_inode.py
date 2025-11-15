from src.inode import Inode, InodeMode

from . import config


def test_encode_decode():
    inode = Inode(InodeMode.DIRECTORY)
    assert Inode.from_bytes(bytearray(inode.to_bytes(config)), config) == inode
