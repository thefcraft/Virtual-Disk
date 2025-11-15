import pytest

from src.virtual_disk.config import Config
from src.virtual_disk.disk import InMemoryDisk
from src.virtual_disk.inode import InodeIO
from src.virtual_disk.path import FileIO, FileMode

from . import assert_disk_not_changed, disk


def test_filemode_basics():
    assert FileMode.READ in FileMode.READ
    assert (FileMode.READ | FileMode.WRITE) & FileMode.READ
    assert (FileMode.READ | FileMode.WRITE) & FileMode.WRITE


@assert_disk_not_changed
def test_create_open_read_write_truncate():
    root = disk.root

    fname = b"testfile"

    f = root.open(fname, mode=FileMode.CREATE | FileMode.READWRITE)
    assert isinstance(f, FileIO)
    with f:
        written = f.write(b"hello")
        assert written == 5
        f.seek(0)
        data = f.read(10)
        assert data == b"hello"
        # truncate to 2 bytes
        f.truncate(2)
        f.seek(0)
        assert f.read(10) == b"he"

    # reopen in read mode and verify contents persisted
    f2 = root.open(fname, mode=FileMode.READ)
    with f2:
        assert f2.read(10) == b"he"

    root.remove(fname)


@assert_disk_not_changed
def test_append_mode_creates_and_appends():
    root = disk.root

    fname = b"appendfile"

    f = root.open(fname, mode=FileMode.APPEND | FileMode.CREATE | FileMode.WRITE)
    with f:
        f.write(b"a")
    # reopen with APPEND and add more
    f2 = root.open(fname, mode=FileMode.APPEND | FileMode.WRITE)
    with f2:
        f2.write(b"bcd")
    # read back
    f3 = root.open(fname, mode=FileMode.READ)
    with f3:
        assert f3.read(10) == b"abcd"
    root.remove(fname)


@assert_disk_not_changed
def test_mkdir_rmdir_and_listdir():
    root = disk.root

    root.mkdir(b"subdir", exist_ok=False)
    assert root.exists(b"subdir")
    assert root.isdir(b"subdir")
    sub = root.chdir(b"subdir")
    # empty dir contains '.' and '..' by design
    listing = sub.listdir(ignore_default=False)
    assert b"." in listing and b".." in listing
    # rmdir
    root.rmdir(b"subdir")
    assert not root.exists(b"subdir")


@assert_disk_not_changed
def test_rename_and_overwrite():
    root = disk.root

    root.open(b"a.txt", mode=FileMode.CREATE | FileMode.WRITE).close()
    root.mkdir(b"dir", exist_ok=True)
    # move a.txt -> dir/b.txt
    root.rename(
        [b".", b"a.txt"], [b".", b"dir", b"b.txt"], overwrite=False
    )  # adapt path style if needed
    assert root.exists(b"dir")
    dest_dir = root.chdir(b"dir")
    assert dest_dir.exists(b"b.txt")

    root.rm_tree(b"dir")


@assert_disk_not_changed
def test_copy_file_and_remove():
    root = disk.root

    with root.open(b"src.bin", mode=FileMode.CREATE | FileMode.WRITE) as s:
        s.write(b"0123456789")
    root.copy_file(
        [b".", b"src.bin"], [b".", b"dst.bin"], overwrite=False, chunk_size=4
    )
    with root.open(b"dst.bin", mode=FileMode.READ) as d:
        assert d.read(20) == b"0123456789"
    root.remove(b"dst.bin")
    assert not root.exists(b"dst.bin")
    root.remove(b"src.bin")


@assert_disk_not_changed
def test_rm_tree_and_copy_tree():
    root = disk.root

    # Create tree: a/ (file f1, subdir b with f2)
    a = root.mkdir(b"a", exist_ok=True)
    with a.open(b"f1", mode=FileMode.CREATE | FileMode.WRITE) as f:
        f.write(b"foo")
    b = a.mkdir(b"b", exist_ok=True)
    with b.open(b"f2", mode=FileMode.CREATE | FileMode.WRITE) as f:
        f.write(b"bar")

    # copy tree a -> a_copy
    root.copy_tree([b"a"], [b".", b"a_copy"], overwrite=False, chunk_size=4)
    assert root.exists(b"a_copy")
    a_copy = root.chdir(b"a_copy")
    assert a_copy.exists(b"f1")
    assert a_copy.isdir(b"b")

    # remove tree
    root.rm_tree(b"a_copy")
    assert not root.exists(b"a_copy")
    root.rm_tree(b"a")


@assert_disk_not_changed
def test_truncate_growth_and_partial_overwrite():
    root = disk.root
    fname = b"growfile"
    with root.open(fname, mode=FileMode.CREATE | FileMode.READWRITE) as f:
        f.write(b"abc")
        f.truncate(10)  # extend file to 10 bytes (should zero-fill)
        f.seek(0)
        data = f.read()
        assert data.startswith(b"abc")
        assert len(data) == 10
        # Overwrite middle part
        f.seek(5)
        f.write(b"XYZ")
        f.seek(0)
        full = f.read()
        assert full[5:8] == b"XYZ"
    root.remove(fname)


@assert_disk_not_changed
def test_open_existing_without_create_raises():
    root = disk.root
    name = b"nofile"
    # opening nonexistent file without CREATE should fail
    with pytest.raises(FileNotFoundError):
        root.open(name, mode=FileMode.READWRITE)


@assert_disk_not_changed
def test_double_rename_and_name_collision():
    root = disk.root
    a = b"a.txt"
    b = b"b.txt"
    c = b"c.txt"
    # prepare two files
    root.open(a, mode=FileMode.CREATE | FileMode.WRITE).close()
    root.open(b, mode=FileMode.CREATE | FileMode.WRITE).close()

    # rename a->c, then b->c should raise FileExistsError
    root.rename([b".", a], [b".", c])
    with pytest.raises(FileExistsError):
        root.rename([b".", b], [b".", c])

    # sanity check: c exists, b still exists
    assert root.exists(b"c.txt")
    assert root.exists(b"b.txt")
    root.remove(b"c.txt")
    root.remove(b"b.txt")


# @assert_disk_not_changed # TODO: prevend from opening same file multiple times maybe raise error, may need global state?
# def test_concurrent_writes_and_reads_share_pointer_independently():
#     root = disk.root
#     fname = b"multiio"
#     with root.open(fname, mode=FileMode.CREATE | FileMode.READWRITE) as f1:
#         f1.write(b"abcde")

#         # open again separately
#         with root.open(fname, mode=FileMode.READWRITE) as f2:
#             f2.seek(2)
#             f2.write(b"Z")
#             # pointer positions should be independent
#             assert f1.tell() == 5
#             assert f2.tell() == 3

#         f1.seek(0)
#         assert f1.read(5) == b"abZde"
#     root.remove(fname)


@assert_disk_not_changed
def test_directory_traversal_nested_depth():
    root = disk.root
    path = [b"deep", b"sub", b"dir"]
    cur = root
    for part in path:
        cur = cur.mkdir(part, exist_ok=True)
        assert cur.isdir(b".")
    # ensure we can reach back to root using chdir("..") repeatedly
    back = cur
    for _ in range(3):
        back = back.chdir(b"..")
    assert back.isdir(b".")
    root.rm_tree(b"deep")


@assert_disk_not_changed
def test_copy_tree_overwrite_false_and_true():
    root = disk.root
    a = root.mkdir(b"A", exist_ok=True)
    with a.open(b"file", mode=FileMode.CREATE | FileMode.WRITE) as f:
        f.write(b"foo")
    b = root.mkdir(b"B", exist_ok=True)
    with b.open(b"file", mode=FileMode.CREATE | FileMode.WRITE) as f:
        f.write(b"bar")
    # overwrite=False should raise
    with pytest.raises(FileExistsError):
        root.copy_tree([b"B"], [b".", b"A"], overwrite=False)
    # overwrite=True should replace
    root.copy_tree([b"B"], [b".", b"A"], overwrite=True)
    with a.open(b"file", mode=FileMode.READ) as f:
        assert f.read() == b"bar"
    root.rm_tree(b"A")
    root.rm_tree(b"B")


@assert_disk_not_changed
def test_remove_nonexistent_file_and_nonempty_dir_errors():
    root = disk.root
    with pytest.raises(FileNotFoundError):
        root.remove(b"missing.bin")

    d = root.mkdir(b"D", exist_ok=True)
    with d.open(b"x", mode=FileMode.CREATE | FileMode.WRITE) as f:
        f.write(b"1")
    with pytest.raises(OSError):
        root.rmdir(b"D")  # nonempty dir
    root.rm_tree(b"D")


@assert_disk_not_changed
def test_zero_byte_file_read_write_seek():
    root = disk.root
    f = root.open(b"zfile", mode=FileMode.CREATE | FileMode.READWRITE)
    with f:
        assert f.read() == b""
        assert f.tell() == 0
        f.write(b"x")
        f.seek(0)
        assert f.read() == b"x"
        f.seek(-1, 1)  # relative seek
        assert f.read() == b"x"  # reading from pos==1 gives b""
    root.remove(b"zfile")


@assert_disk_not_changed
def test_multiple_create_flags_and_recreate_behavior():
    root = disk.root
    name = b"dup"
    f = root.open(name, mode=FileMode.CREATE | FileMode.WRITE)
    f.write(b"123")
    f.close()

    # opening again with CREATE | TRUNCATE equivalent should reset content
    f2 = root.open(name, mode=FileMode.CREATE | FileMode.TRUNCATE | FileMode.READWRITE)
    f2.write(b"9")
    f2.seek(0)
    assert f2.read() == b"9"
    f2.close()
    root.remove(name)


@assert_disk_not_changed
def test_large_file():
    root = disk.root
    data = bytearray(i % 255 for i in range(1024 * 1024))  # 1 MB
    repeate = 4
    with root.open(
        b"home.txt", FileMode.WRITE | FileMode.CREATE | FileMode.EXCLUSIVE
    ) as f:
        for _ in range(repeate):
            f.write(data)
    with root.open(b"home.txt") as f:
        for _ in range(repeate):
            assert f.read(1024 * 1024) == data
    root.remove(b"home.txt")


@assert_disk_not_changed
def test_large_file_again():
    root = disk.root
    data = bytearray(i % 255 for i in range(4))
    repeate = 1024
    with root.open(
        b"home.txt", FileMode.WRITE | FileMode.CREATE | FileMode.EXCLUSIVE
    ) as f:
        for _ in range(repeate):
            f.write(data)
    with root.open(b"home.txt") as f:
        for _ in range(repeate):
            assert f.read(4) == data
    root.remove(b"home.txt")


@assert_disk_not_changed
def test_large_inode():
    root = disk.root

    result = root.create_empty_file(b"some.txt")

    num_entrys = 512

    inode_io = InodeIO(result.inode, disk=disk)

    assert inode_io.read_at(0) == b""

    pos = 0
    for i in range(num_entrys):
        name = f"file-{i:_<5}.txt\n".encode("utf-8")
        inode_io.write_at(pos, name)
        pos += len(name)

    inode_io.read_at(0)

    inode_io.truncate_to(0)

    assert inode_io.read_at(0) == b""

    root.remove(b"some.txt")


def test_some():
    config = Config(block_size=512, inode_size=48, num_blocks=512, num_inodes=512)

    disk = InMemoryDisk(config=config)

    # print(disk.inodes_bitmap) # 1
    # print(disk.blocks_bitmap) # 1 1

    num_entrys = 512 * 16

    pos = 0
    for i in range(num_entrys):
        name = f"file-{i:_<5}.txt".encode("utf-8")

        pos += disk.root.inode_io.write_at(pos=pos, data=name)
        # for i in range(len(name)):
        # pos += disk.root.inode_io.write_at(pos=pos, data=name[i:i+1])

    disk.root.inode_io.read_at(pos=0, n=-1)


# @assert_disk_not_changed
# def test_many_entry():
#     root = disk.root
#     num_entrys = 256

#     NAME_REPR_LEN = 1

#     with FileIO(
#         disk=disk,
#         inode_ptr=root.inode_ptr,
#         inode=root.inode_io.inode,
#         mode=FileMode.READWRITE
#     ) as f:
#         for i in range(num_entrys):
#             # root._add_entry(f"file-{i:_<5}.txt".encode('utf-8'), 0)

#             name = f"file-{i:_<5}.txt".encode('utf-8')
#             inode_ptr = 0

#             entry_data = len(name).to_bytes(
#                 length=NAME_REPR_LEN,
#                 byteorder='big',
#                 signed=False
#             ) + name + inode_ptr.to_bytes(
#                 length=disk.config.inode_addr_length,
#                 byteorder='big',
#                 signed=False
#             )
#             f.write(entry_data)
#             pos = f.tell()
#             f.seek(0)
#             f.read()
#             f.seek(pos)
#     with FileIO(
#         disk=disk,
#         inode_ptr=root.inode_ptr,
#         inode=root.inode_io.inode,
#         mode=FileMode.READWRITE
#     ) as f:
#         f.read()

#     root.inode_io.read_at(0)

#     for i in range(num_entrys):
#         root._remove_entry(f"file-{i:_<5}.txt".encode('utf-8'))


# @assert_disk_not_changed
# def test_many_files():
#     root = disk.root

#     per_file_name_len = len(f"file-{0:_<5}.txt".encode('utf-8'))
#     num_files = 256

#     # print(per_file_name_len * 256 + 256)

#     for i in range(num_files):
#         root.create_empty_file(f"file-{i:_<5}.txt".encode('utf-8'))
#     # TODO: error caused by name len store in the inode and using inode ptr
#     # items = list(root.inode_io.iteritem())
#     # assert len(items) == num_files, f"{len(items)=} != {num_files=}"
#     for i in range(num_files):
#         root.remove(f"file-{i:_<5}.txt".encode('utf-8'))
