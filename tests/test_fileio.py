from src.virtual_disk.inode import Inode, InodeMode
from src.virtual_disk.path import FileIO

from . import assert_disk_not_changed, disk


@assert_disk_not_changed
def test_read_write():
    inode = Inode(st_mode=InodeMode.REGULAR_FILE)

    f = FileIO(disk, 1, inode)
    with f:
        assert f.read(-1) == b""
        data = b"h" * 1024 * 1024 * 32
        f.write(data)
        f.seek(0)
        assert f.read() == data
        f.truncate(0)
        assert f.read(-1) == b""
