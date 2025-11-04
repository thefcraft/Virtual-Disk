from . import disk, assert_disk_not_changed
from src.inode import Inode, InodeIO, InodeMode

@assert_disk_not_changed
def test_read_write():
    root = Inode(
        st_mode=InodeMode.REGULAR_FILE
    )
    root_io = InodeIO(root, disk)
    
    assert root_io.read_at(0, n=-1) == b''
    data = b'h'*1024*1024*32
    root_io.write_at(0, data)
    assert root_io.read_at(0, n=-1) == data
    root_io.truncate_to(st_size=0)
    assert root_io.read_at(0, n=-1) == b''
    