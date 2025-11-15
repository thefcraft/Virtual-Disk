from src.inode import Inode, InodeIO, InodeMode
from src.path import Directory

from . import assert_disk_not_changed, disk


@assert_disk_not_changed
def test_entry():
    inode = Inode(InodeMode.DIRECTORY)
    inode_io = InodeIO(inode, disk)
    root = Directory(disk, inode=inode, inode_ptr=0)

    assert inode_io.read_at(0) == b""
    assert len(list(root._iter_entries())) == 0

    root._add_entry(b".", inode_ptr=0)
    assert len(list(root._iter_entries())) == 1
    assert root._find_entry(b".") == 0

    root._add_entry(b"..", inode_ptr=0)
    assert len(list(root._iter_entries())) == 2
    assert root._find_entry(b".") == 0
    assert root._find_entry(b"..") == 0

    root._remove_entry(b".")

    assert len(list(root._iter_entries())) == 1
    assert root._find_entry(b"..") == 0

    root._remove_entry(b"..")

    assert inode_io.read_at(0) == b""
    assert len(list(root._iter_entries())) == 0
